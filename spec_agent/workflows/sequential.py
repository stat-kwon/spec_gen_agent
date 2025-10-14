"""
순차 명세 생성 워크플로우.
"""

import inspect
import json
import logging
import time
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from spec_agent.config import Config
from spec_agent.models import ServiceType
from spec_agent.tools import (
    load_frs_document,
    validate_markdown_structure,
    validate_openapi_spec,
    apply_template,
)
from spec_agent.utils.logging import (
    configure_logging,
    get_agent_logger,
    get_session_logger,
)

from .context import WorkflowContext
from .generation import SequentialDocumentGenerator
from .git_ops import commit_generated_changes, setup_git_branch
from .quality import QualityImprovementManager


class SequentialWorkflow:
    """순차 명세 생성 워크플로우 구현."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.from_env()
        self.config.validate()

        self.context = WorkflowContext()
        self.agents: Dict[str, Any] = {}
        self.saved_files: List[str] = []

        self.session_id = f"spec-{int(time.time())}"
        configure_logging(self.config.log_level)
        self.logger = get_session_logger("workflow", self.session_id)
        self._agent_loggers: Dict[str, logging.LoggerAdapter] = {}

        self.generator: Optional[SequentialDocumentGenerator] = None
        self.quality_manager: Optional[QualityImprovementManager] = None

        self.logger.info("워크플로우 초기화 완료")

    def _tool_kwargs(self, tool_fn):
        """도구 함수 호출 시 session_id 지원 여부에 따라 kwargs 제공."""

        try:
            signature = inspect.signature(tool_fn)
        except (TypeError, ValueError):
            return {}

        if "session_id" in signature.parameters:
            return {"session_id": self.session_id}

        return {}

    def _initialize_agents(self) -> None:
        """에이전트를 초기화합니다."""

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

        self.logger.info("에이전트 초기화 시작")
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

        self._reconfigure_components()

        self.logger.info("%d개 에이전트 초기화 완료", len(self.agents))

    def _get_agent_logger(self, agent_name: str) -> logging.LoggerAdapter:
        """세션 컨텍스트와 함께 에이전트 로거를 반환합니다."""

        if agent_name not in self._agent_loggers:
            self._agent_loggers[agent_name] = get_agent_logger(
                self.session_id, agent_name
            )
        return self._agent_loggers[agent_name]

    def _reconfigure_components(self) -> None:
        """에이전트 의존 컴포넌트를 재구성합니다."""

        if not self.agents:
            raise ValueError("에이전트가 구성되지 않았습니다.")

        self.generator = SequentialDocumentGenerator(
            context=self.context,
            agents=self.agents,
            logger=self.logger,
            agent_logger_factory=self._get_agent_logger,
            process_agent_result=self._process_agent_result,
            validate_and_record=self._validate_and_record_template,
            save_document=self._save_agent_document_sync,
        )

        self.quality_manager = QualityImprovementManager(
            context=self.context,
            agents=self.agents,
            logger=self.logger,
            agent_logger_factory=self._get_agent_logger,
            document_order=self._get_document_agent_order,
            process_agent_result=self._process_agent_result,
            validate_and_record=self._validate_and_record_template,
            save_document=self._save_agent_document_sync,
            max_iterations=getattr(self.config, "max_iterations", 1),
            quality_threshold=getattr(self.config, "quality_threshold", 0.0),
        )

    def _ensure_components_ready(self) -> None:
        """생성기/품질 매니저가 준비되었는지 확인합니다."""

        if self.generator is None or self.quality_manager is None:
            if not self.agents:
                raise RuntimeError(
                    "에이전트가 설정되지 않아 컴포넌트를 구성할 수 없습니다."
                )
            self._reconfigure_components()

    async def execute_workflow(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str] = None,
        use_git: bool = True,
    ) -> Dict[str, Any]:
        """워크플로우를 실행합니다."""

        start_time = time.time()
        try:
            self.logger.info("FRS 로드 시작 | 경로: %s", frs_path)
            await self._initialize_project(frs_path, service_type, output_dir)
            self.logger.info("FRS 로드 완료 | 서비스 유형: %s", service_type.value)

            if use_git:
                setup_git_branch(
                    self.context,
                    self._tool_kwargs,
                    self.logger,
                )

            self._initialize_agents()
            self._ensure_components_ready()
            workflow_result = await self.generator.run(service_type)

            if workflow_result.get("success"):
                quality_cycle_result = await self.quality_manager.run(service_type)
            else:
                quality_cycle_result = {
                    "iterations": [],
                    "improvement_applied": False,
                    "updated_files": [],
                    "skipped": True,
                    "reason": "sequential_generation_failed",
                }

            files_written = (
                list(dict.fromkeys(self.saved_files))
                if self.saved_files
                else workflow_result.get("saved_files", [])
            )

            if use_git and files_written:
                commit_generated_changes(
                    self.context,
                    files_written,
                    self._tool_kwargs,
                    self.logger,
                )

            execution_time = time.time() - start_time
            self.logger.info(
                "워크플로우 완료 | 생성 파일 %d개 | 실행 시간 %.2f초",
                len(files_written),
                execution_time,
            )

            return {
                "success": True,
                "session_id": self.session_id,
                "output_dir": self.context.project.get("output_dir"),
                "files_written": files_written,
                "workflow_result": workflow_result,
                "quality_cycle": quality_cycle_result,
                "execution_time": execution_time,
                "framework": "Strands Agent SDK - Sequential",
            }

        except Exception as exc:
            error_msg = f"워크플로우 실행 실패: {str(exc)}"
            self.logger.exception("워크플로우 실행 실패")

            partial_files = list(self.saved_files)
            return {
                "success": False,
                "session_id": self.session_id,
                "error": error_msg,
                "execution_time": time.time() - start_time,
                "files_written": partial_files,
                "partial_success": len(partial_files) > 0,
            }

    async def _execute_sequential_workflow(
        self, service_type: ServiceType
    ) -> Dict[str, Any]:
        """기존 호환성을 위한 순차 실행 래퍼."""

        self._ensure_components_ready()
        return await self.generator.run(service_type)

    async def _run_quality_improvement_cycle(
        self, service_type: ServiceType
    ) -> Dict[str, Any]:
        """기존 호환성을 위한 품질 사이클 래퍼."""

        self._ensure_components_ready()
        return await self.quality_manager.run(service_type)

    def _parse_json_response(self, agent_name: str, response: Any) -> Dict[str, Any]:
        """기존 호환성을 위한 JSON 응답 파서."""

        if response is None:
            return {}

        if isinstance(response, dict):
            return response

        text = str(response).strip()
        if not text:
            return {}

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                first_line = lines.pop(0)
                if first_line.lower().startswith("```json"):
                    pass
            if lines and lines[-1].startswith("```"):
                lines.pop()
            text = "\n".join(lines).strip()

        decoder = json.JSONDecoder()
        try:
            return decoder.decode(text)
        except json.JSONDecodeError:
            for idx, ch in enumerate(text):
                if ch in "[{":
                    try:
                        parsed, _ = decoder.raw_decode(text[idx:])
                        return parsed
                    except json.JSONDecodeError:
                        continue

        self._get_agent_logger(agent_name).warning(
            "JSON 파싱 실패 - 원문을 raw_response로 저장합니다"
        )
        return {"raw_response": text}

    async def _initialize_project(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str],
    ) -> None:
        """프로젝트 기본 정보를 준비합니다."""

        frs_result = load_frs_document(
            frs_path,
            **self._tool_kwargs(load_frs_document),
        )
        if not frs_result.get("success"):
            raise ValueError(f"FRS 로드 실패: {frs_path}")

        frs_id = self._extract_frs_id(frs_path)
        resolved_output = output_dir or f"specs/{frs_id}/{service_type.value}"

        self.context.project = {
            "frs_path": frs_path,
            "frs_id": frs_id,
            "frs_content": frs_result.get("content", ""),
            "service_type": service_type.value,
            "output_dir": resolved_output,
        }

        Path(resolved_output).mkdir(parents=True, exist_ok=True)
        self.logger.info(
            "출력 디렉토리 준비 완료 | 경로: %s",
            self.context.project["output_dir"],
        )

    def _get_document_agent_order(self, service_type: ServiceType) -> List[str]:
        """문서 생성/개선 순서를 반환합니다."""

        order = ["requirements", "design", "tasks", "changes"]
        if service_type == ServiceType.API:
            order.append("openapi")
        return order

    def _process_agent_result(self, agent_name: str, result: Any) -> str:
        """에이전트 결과를 문자열로 정규화합니다."""

        if agent_name == "openapi" and isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)

        result_str = str(result)
        if agent_name == "openapi":
            if result_str.startswith("```json"):
                result_str = result_str[7:]
            if result_str.startswith("```"):
                result_str = result_str[3:]
            if result_str.endswith("```"):
                result_str = result_str[:-3]
            result_str = result_str.strip()

            try:
                parsed = json.loads(result_str)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "OpenAPI 결과를 JSON으로 파싱하는 데 실패했습니다: "
                    f"{exc.msg} (line {exc.lineno}, column {exc.colno})"
                ) from exc

            return json.dumps(parsed, ensure_ascii=False, indent=2)

        return result_str

    def _validate_and_record_template(
        self,
        agent_name: str,
        content: str,
    ) -> Dict[str, Any]:
        """템플릿 검증을 수행하고 컨텍스트에 기록합니다."""

        agent_logger = self._get_agent_logger(agent_name)
        template_type = "openapi" if agent_name == "openapi" else agent_name

        try:
            if agent_name == "openapi":
                template_result = validate_openapi_spec(
                    content,
                    **self._tool_kwargs(validate_openapi_spec),
                )
            else:
                template_result = apply_template(
                    content,
                    template_type,
                    **self._tool_kwargs(apply_template),
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

    def _save_agent_document_sync(
        self,
        agent_name: str,
        content: str,
    ) -> Optional[Dict[str, Any]]:
        """생성 문서를 동기적으로 저장합니다."""

        agent_logger = self._get_agent_logger(agent_name)
        try:
            output_dir = self.context.project["output_dir"]

            filename = "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
            file_path = Path(output_dir) / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)

            is_update = file_path.exists()
            action = "업데이트" if is_update else "생성"

            with open(file_path, "w", encoding="utf-8") as file_obj:
                file_obj.write(content)

            file_size = file_path.stat().st_size
            agent_logger.info(
                "문서 저장 완료 | 파일: %s | 작업: %s | 크기: %d bytes",
                str(file_path),
                action,
                file_size,
            )

            file_path_str = str(file_path)
            if file_path_str not in self.saved_files:
                self.saved_files.append(file_path_str)

            return {
                "filename": filename,
                "file_path": file_path_str,
                "size": file_size,
                "action": action,
            }

        except Exception:
            agent_logger.exception("문서 저장 중 오류 발생")
            return None

    def validate_existing_specs(self, spec_dir: str) -> Dict[str, Any]:
        """기존 명세 파일을 검증합니다."""

        try:
            spec_path = Path(spec_dir)
            if not spec_path.exists() or not spec_path.is_dir():
                return {
                    "success": False,
                    "error": f"디렉토리를 찾을 수 없음: {spec_dir}",
                }

            validation_results = []
            files_to_validate = [
                "requirements.md",
                "design.md",
                "tasks.md",
                "changes.md",
                "openapi.json",
            ]

            for file_name in files_to_validate:
                file_path = spec_path / file_name
                if not file_path.exists():
                    validation_results.append(
                        {
                            "file": file_name,
                            "file_path": str(file_path),
                            "exists": False,
                            "valid": False,
                            "error": "파일이 존재하지 않음",
                        }
                    )
                    continue

                if file_name.endswith(".md"):
                    result = validate_markdown_structure(str(file_path))
                elif file_name.endswith(".json"):
                    result = validate_openapi_spec(str(file_path))
                else:
                    result = {"success": True}

                validation_results.append(
                    {
                        "file": file_name,
                        "file_path": str(file_path),
                        "exists": True,
                        "valid": result.get("success", False),
                        "error": result.get("error"),
                    }
                )

            total_files = len(validation_results)
            valid_files = sum(1 for r in validation_results if r["valid"])
            return {
                "success": True,
                "validation_results": validation_results,
                "summary": {
                    "total_files": total_files,
                    "valid_files": valid_files,
                    "invalid_files": total_files - valid_files,
                },
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _extract_frs_id(self, frs_path: str) -> str:
        """FRS 파일 경로에서 ID를 추출합니다."""

        match = re.search(r"FRS-(\d+)", frs_path)
        if match:
            return f"FRS-{match.group(1)}"
        return Path(frs_path).stem
