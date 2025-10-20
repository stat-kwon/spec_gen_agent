"""명세 생성 전체 워크플로우."""

from __future__ import annotations

import ast
import inspect
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from spec_agent.config import Config
from spec_agent.models import ServiceType
from spec_agent.tools import apply_template, load_frs_document, validate_openapi_spec
from spec_agent.utils.logging import (
    configure_logging,
    get_agent_logger,
    get_session_logger,
)

from .context import WorkflowContext
from .generation import DocumentGenerationPhase
from .git_ops import commit_generated_changes, setup_git_branch
from .quality_feedback.phase import QualityFeedbackPhase
from .quality_improvement.phase import QualityImprovementPhase
from .storage import SpecStorage
from .utils.feedback_tracker import FeedbackTracker


class SpecificationWorkflowRunner:
    """FRS로부터 명세 문서를 생성·검증하는 워크플로우."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.from_env()
        self.config.validate()

        self.context = WorkflowContext()
        self.session_id = f"spec-{int(time.time())}"

        configure_logging(self.config.log_level)
        self.logger = get_session_logger("workflow", self.session_id)

        self.storage = SpecStorage(self.context)
        self.feedback_tracker = FeedbackTracker(self.context)

        self.agents: Dict[str, Any] = {}
        self._agent_loggers: Dict[str, logging.LoggerAdapter] = {}

        self.document_phase: Optional[DocumentGenerationPhase] = None
        self.quality_phase: Optional[QualityImprovementPhase] = None
        self.feedback_phase: Optional[QualityFeedbackPhase] = None

        self.logger.info("워크플로우 러너 초기화 완료")

    async def run(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str] = None,
        use_git: bool = True,
    ) -> Dict[str, Any]:
        start_time = time.time()
        try:
            self.logger.info("FRS 로드 시작 | 경로: %s", frs_path)
            await self._prepare_project(frs_path, service_type, output_dir)
            self.logger.info("FRS 로드 완료 | 서비스 유형: %s", service_type.value)

            if use_git:
                setup_git_branch(
                    self.context,
                    self._tool_kwargs,
                    self.logger,
                )

            self._initialize_agents()
            self._initialize_phases()

            generation_result = await self.document_phase.execute(service_type)  # type: ignore[arg-type]

            if generation_result.get("success"):
                quality_result = self._run_quality_cycle(service_type)
            else:
                quality_result = {
                    "iterations": [],
                    "improvement_applied": False,
                    "updated_files": [],
                    "skipped": True,
                    "reason": "generation_failed",
                }

            saved_files = self.storage.saved_files()
            if use_git and saved_files:
                commit_generated_changes(
                    self.context,
                    saved_files,
                    self._tool_kwargs,
                    self.logger,
                )

            execution_time = time.time() - start_time
            self.logger.info(
                "워크플로우 완료 | 생성 파일 %d개 | 실행 시간 %.2f초",
                len(saved_files),
                execution_time,
            )

            return {
                "success": True,
                "session_id": self.session_id,
                "output_dir": self.context.project.get("output_dir"),
                "files_written": saved_files,
                "generation": generation_result,
                "quality": quality_result,
                "execution_time": execution_time,
                "framework": "SpecificationPipeline",
            }

        except Exception as exc:
            self.logger.exception("워크플로우 실행 실패")
            return {
                "success": False,
                "session_id": self.session_id,
                "error": f"워크플로우 실행 실패: {exc}",
                "execution_time": time.time() - start_time,
                "files_written": self.storage.saved_files(),
            }

    # ------------------------------------------------------------------ #
    # 초기화
    # ------------------------------------------------------------------ #

    async def _prepare_project(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str],
    ) -> None:
        frs_result = load_frs_document(
            frs_path,
            **self._tool_kwargs(load_frs_document),
        )
        if not frs_result.get("success"):
            raise ValueError(f"FRS 로드 실패: {frs_path}")

        frs_id = self._extract_frs_id(frs_path)
        resolved_output = output_dir or f"specs/{frs_id}/{service_type.value}"
        resolved_output = self.storage.prepare_output_directory(resolved_output)

        self.context.project = {
            "frs_path": frs_path,
            "frs_id": frs_id,
            "frs_content": frs_result.get("content", ""),
            "service_type": service_type.value,
            "output_dir": resolved_output,
        }

    def _initialize_agents(self) -> None:
        from spec_agent.agents import (
            create_changes_agent,
            create_consistency_checker_agent,
            create_coordinator_agent,
            create_design_agent,
            create_openapi_agent,
            create_quality_assessor_agent,
            create_requirements_agent,
            create_tasks_agent,
        )

        self.logger.info("에이전트 초기화")
        self.agents = {
            "requirements": create_requirements_agent(
                self.config, session_id=self.session_id
            ),
            "design": create_design_agent(self.config, session_id=self.session_id),
            "tasks": create_tasks_agent(self.config, session_id=self.session_id),
            "changes": create_changes_agent(self.config, session_id=self.session_id),
            "openapi": create_openapi_agent(self.config, session_id=self.session_id),
            "quality_assessor": create_quality_assessor_agent(self.config),
            "consistency_checker": create_consistency_checker_agent(self.config),
            "coordinator": create_coordinator_agent(self.config),
        }

        self._agent_loggers = {
            name: get_agent_logger(self.session_id, name) for name in self.agents
        }

    def _initialize_phases(self) -> None:
        self.document_phase = DocumentGenerationPhase(
            context=self.context,
            agents=self.agents,
            logger=self.logger,
            agent_logger_factory=self._get_agent_logger,
            process_agent_result=self._process_agent_result,
            validate_and_record=self._validate_and_record_template,
            save_document=self._save_document,
        )

        self.quality_phase = QualityImprovementPhase(
            context=self.context,
            agents=self.agents,
            logger=self.logger,
            agent_logger_factory=self._get_agent_logger,
            document_order=self._get_document_agent_order,
            feedback_tracker=self.feedback_tracker,
            max_iterations=getattr(self.config, "max_iterations", 1),
            quality_threshold=getattr(self.config, "quality_threshold", 0.0),
        )

        self.feedback_phase = QualityFeedbackPhase(
            context=self.context,
            agents=self.agents,
            logger=self.logger,
            agent_logger_factory=self._get_agent_logger,
            document_order=self._get_document_agent_order,
            process_agent_result=self._process_agent_result,
            validate_and_record=self._validate_and_record_template,
            save_document=self._save_document,
            feedback_tracker=self.feedback_tracker,
        )

    # ------------------------------------------------------------------ #
    # 공용 헬퍼
    # ------------------------------------------------------------------ #

    def _tool_kwargs(self, tool_fn):
        try:
            signature = inspect.signature(tool_fn)
        except (TypeError, ValueError):
            return {}

        if "session_id" in signature.parameters:
            return {"session_id": self.session_id}
        return {}

    def _get_agent_logger(self, agent_name: str) -> logging.LoggerAdapter:
        if agent_name not in self._agent_loggers:
            self._agent_loggers[agent_name] = get_agent_logger(
                self.session_id, agent_name
            )
        return self._agent_loggers[agent_name]

    @staticmethod
    def _extract_frs_id(frs_path: str) -> str:
        stem = Path(frs_path).stem
        if "-" in stem:
            return stem.split("-", 1)[0]
        return stem

    def _get_document_agent_order(self, service_type: ServiceType) -> List[str]:
        order = ["requirements", "design", "tasks", "changes"]
        if service_type == ServiceType.API:
            order.append("openapi")
        return order

    def _run_quality_cycle(self, service_type: ServiceType) -> Dict[str, Any]:
        if not self.quality_phase or not self.feedback_phase:
            raise RuntimeError("품질 단계가 초기화되지 않았습니다.")

        self.logger.info("품질 평가 단계 시작")
        self.quality_phase.reset()

        cycle_results: List[Dict[str, Any]] = []
        improvement_applied = False
        cumulative_updated_files: List[str] = []

        iteration_limit = getattr(self.quality_phase, "max_iterations", 1)

        for iteration in range(1, iteration_limit + 1):
            iteration_result, should_continue = self.quality_phase.evaluate_iteration(
                service_type,
                iteration,
            )
            if iteration_result is None:
                self.logger.warning("품질 평가 루프 종료 - 검토할 문서가 없습니다")
                break

            iteration_summary = {
                "iteration": iteration,
                "quality": iteration_result.quality,
                "consistency": iteration_result.consistency,
                "coordinator": iteration_result.coordinator,
            }
            cycle_results.append(iteration_summary)

            iteration_snapshot = {
                "iteration": iteration,
                "quality": iteration_result.quality,
                "consistency": iteration_result.consistency,
                "coordinator": iteration_result.coordinator,
                "feedback_by_doc": iteration_result.feedback_by_doc.copy(),
            }
            self.context.quality["previous_results"] = iteration_snapshot

            if not should_continue:
                self.logger.info("품질 평가 단계 종료 - 추가 개선 불필요")
                break

            feedback_outcome = self.feedback_phase.apply_feedback(
                documents=iteration_result.documents,
                feedback_by_doc=iteration_result.feedback_by_doc,
                service_type=service_type,
                iteration=iteration,
            )

            iteration_snapshot["filtered_feedback"] = feedback_outcome[
                "filtered_feedback"
            ]
            if feedback_outcome["skipped_feedback"]:
                iteration_snapshot["skipped_feedback"] = feedback_outcome[
                    "skipped_feedback"
                ]
            iteration_snapshot["applied_files"] = feedback_outcome["updated_files"]
            self.context.quality["previous_results"] = iteration_snapshot

            updated_files = feedback_outcome["updated_files"]
            if not updated_files:
                self.logger.warning("품질 개선 단계 - 문서 갱신 실패, 루프 종료")
                break

            improvement_applied = True
            cumulative_updated_files.extend(updated_files)

        summary = {
            "iterations": cycle_results,
            "improvement_applied": improvement_applied,
            "updated_files": list(dict.fromkeys(cumulative_updated_files)),
        }

        self.context.quality["cycle_results"] = cycle_results
        self.context.quality["improvement_applied"] = improvement_applied
        self.context.quality.pop("verified_feedback", None)

        return summary

    def _process_agent_result(self, agent_name: str, result: Any) -> str:
        result_str = str(result)
        if agent_name == "openapi":
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False, indent=2)

            if result_str.startswith("```json"):
                result_str = result_str[7:]
            if result_str.startswith("```"):
                result_str = result_str[3:]
            if result_str.endswith("```"):
                result_str = result_str[:-3]
            result_str = result_str.strip()

            parsed = self._parse_json_with_repair(result_str)
            return json.dumps(parsed, ensure_ascii=False, indent=2)

        return result_str

    def _parse_json_with_repair(self, content: str) -> Any:
        candidate = self._extract_json_candidate(content)

        def _safe_python_eval(text: str) -> Optional[Any]:
            try:
                tree = ast.parse(text, mode="eval")
            except SyntaxError:
                return None

            def _convert(node: ast.AST) -> Any:
                if isinstance(node, ast.Constant):
                    value = node.value
                    if isinstance(value, (str, int, float, bool, type(None))):
                        return value
                    raise ValueError
                if isinstance(node, ast.Dict):
                    return {
                        _convert(key): _convert(value)
                        for key, value in zip(node.keys, node.values)
                    }
                if isinstance(node, ast.List):
                    return [_convert(element) for element in node.elts]
                if isinstance(node, ast.Tuple):
                    return [_convert(element) for element in node.elts]
                if isinstance(node, ast.UnaryOp) and isinstance(
                    node.op, (ast.UAdd, ast.USub)
                ):
                    operand = _convert(node.operand)
                    if isinstance(operand, (int, float)):
                        return operand if isinstance(node.op, ast.UAdd) else -operand
                    raise ValueError
                if isinstance(node, ast.Name):
                    lowered = node.id.lower()
                    if lowered == "true":
                        return True
                    if lowered == "false":
                        return False
                    if lowered in {"null", "none"}:
                        return None
                    raise ValueError
                raise ValueError

            try:
                value = _convert(tree.body)
            except ValueError:
                return None

            return value if isinstance(value, (dict, list)) else None

        def _try_parsers(text: str) -> Optional[Any]:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                return parsed
            return _safe_python_eval(text)

        parsed = _try_parsers(candidate)
        if parsed is not None:
            return parsed

        repaired = candidate.replace("\r", "")
        key_pattern = re.compile(r'(?<=\{|,)\s*(?!")([A-Za-z0-9_\-\$]+)\s*:')
        repaired = key_pattern.sub(lambda m: f'"{m.group(1)}":', repaired)

        parsed = _try_parsers(repaired)
        if parsed is not None:
            return parsed

        try:
            parsed_value = json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "OpenAPI 결과를 JSON으로 파싱하는 데 실패했습니다: "
                f"{exc.msg} (line {exc.lineno}, column {exc.colno})"
            ) from exc

        raise ValueError(
            "OpenAPI 결과가 객체 또는 배열 JSON 형식이 아닙니다: "
            f"{type(parsed_value).__name__}"
        )

    @staticmethod
    def _extract_json_candidate(text: str) -> str:
        start_index: Optional[int] = None
        end_index: Optional[int] = None
        stack: List[str] = []
        in_string = False
        escape = False

        for idx, ch in enumerate(text):
            if start_index is None:
                if ch in "[{":
                    start_index = idx
                    stack.append("}" if ch == "{" else "]")
                continue

            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch in "[{":
                stack.append("}" if ch == "{" else "]")
                continue

            if ch in "}]" and stack:
                expected = stack.pop()
                if ch != expected:
                    return text.strip()
                if not stack:
                    end_index = idx + 1
                    break

        if start_index is not None and end_index is not None:
            return text[start_index:end_index]
        return text.strip()

    def _validate_and_record_template(
        self,
        agent_name: str,
        content: str,
    ) -> Dict[str, Any]:
        agent_logger = self._get_agent_logger(agent_name)
        template_type = "openapi" if agent_name == "openapi" else agent_name

        try:
            if agent_name == "openapi":
                validator = self._get_validate_openapi_spec_fn()
                template_result = validator(
                    content,
                    **self._tool_kwargs(validator),
                )
            else:
                template_fn = self._get_apply_template_fn()
                template_result = template_fn(
                    content,
                    template_type,
                    **self._tool_kwargs(template_fn),
                )
        except Exception:
            agent_logger.exception("템플릿 검증 도구 호출 실패")
            raise

        self.context.documents.previous_contents[agent_name] = content
        self.context.documents.template_results[agent_name] = template_result
        self.context.metrics.setdefault("template_checks", {})[
            agent_name
        ] = template_result

        if not isinstance(template_result, dict):
            raise ValueError(f"템플릿 검증 결과가 올바르지 않습니다: {template_result}")

        if not template_result.get("success", False):
            missing_sections = template_result.get("missing_sections", [])
            error_message = template_result.get("error")
            detail = ""
            if error_message:
                detail = error_message
            elif missing_sections:
                detail = f"누락된 섹션: {', '.join(missing_sections)}"
            else:
                detail = "템플릿 검증에 실패했습니다."

            agent_logger.error("템플릿 검증 실패 | 상세: %s", detail)
            raise ValueError(f"{agent_name} 템플릿 검증 실패: {detail}")

        return template_result

    def _save_document(
        self,
        agent_name: str,
        content: str,
    ) -> Optional[Dict[str, Any]]:
        agent_logger = self._get_agent_logger(agent_name)
        try:
            result = self.storage.write_document(agent_name, content)
            agent_logger.info(
                "문서 저장 완료 | 파일: %s | 작업: %s | 크기: %d bytes",
                result["file_path"],
                result["action"],
                result["size"],
            )
            return result
        except Exception:
            agent_logger.exception("문서 저장 중 오류 발생")
            return None

    def _get_apply_template_fn(self):
        return apply_template

    def _get_validate_openapi_spec_fn(self):
        return validate_openapi_spec
