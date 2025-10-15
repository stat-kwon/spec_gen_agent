import json
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from spec_agent.models import ServiceType

from .context import WorkflowContext
from .prompts import (
    build_consistency_review_prompt,
    build_coordinator_prompt,
    build_improvement_prompt,
    build_quality_review_prompt,
    pair_required_sections,
)

AgentCallable = Callable[[Any], Any]
AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
ProcessResultFn = Callable[[str, Any], str]
ValidateTemplateFn = Callable[[str, str], Dict[str, Any]]
SaveDocumentFn = Callable[[str, str], Optional[Dict[str, Any]]]
DocumentOrderFn = Callable[[ServiceType], List[str]]


class QualityImprovementManager:
    """품질 향상 사이클을 수행합니다."""

    def __init__(
        self,
        context: WorkflowContext,
        agents: Dict[str, AgentCallable],
        logger: logging.LoggerAdapter,
        agent_logger_factory: AgentLoggerFactory,
        document_order: DocumentOrderFn,
        process_agent_result: ProcessResultFn,
        validate_and_record: ValidateTemplateFn,
        save_document: SaveDocumentFn,
        max_iterations: int,
        quality_threshold: float,
    ) -> None:
        self.context = context
        self.agents = agents
        self.logger = logger
        self.agent_logger_factory = agent_logger_factory
        self.document_order = document_order
        self.process_agent_result = process_agent_result
        self.validate_and_record = validate_and_record
        self.save_document = save_document
        self.max_iterations = max(1, max_iterations)
        self.quality_threshold = quality_threshold

    async def run(self, service_type: ServiceType) -> Dict[str, Any]:
        """품질 개선 사이클을 실행합니다."""

        self.logger.info("품질 개선 사이클 시작")

        cycle_results: List[Dict[str, Any]] = []
        improvement_applied = False
        cumulative_updated_files: List[str] = []

        # 이전 평가 결과 초기화
        self.context.quality.pop("previous_results", None)

        for iteration in range(1, self.max_iterations + 1):
            documents = self._load_generated_documents(service_type)
            if not documents:
                self.logger.warning("품질 개선 사이클 중단 - 로드된 문서가 없습니다")
                break

            review_payload = self._format_documents_for_review(documents, service_type)

            quality_prompt = build_quality_review_prompt(
                self.context.project.get("output_dir", ""), review_payload
            )
            quality_raw = self.agents["quality_assessor"](quality_prompt)
            quality_result = self._parse_json_response("quality_assessor", quality_raw)

            consistency_prompt = build_consistency_review_prompt(
                self.context.project.get("output_dir", ""), review_payload
            )
            consistency_raw = self.agents["consistency_checker"](consistency_prompt)
            consistency_result = self._parse_json_response(
                "consistency_checker", consistency_raw
            )

            coordinator_prompt = build_coordinator_prompt(
                self.context.project.get("output_dir", ""),
                review_payload,
                quality_result,
                consistency_result,
            )
            coordinator_raw = self.agents["coordinator"](coordinator_prompt)
            coordinator_result = self._parse_json_response(
                "coordinator", coordinator_raw
            )

            iteration_result = {
                "iteration": iteration,
                "quality": quality_result,
                "consistency": consistency_result,
                "coordinator": coordinator_result,
            }
            cycle_results.append(iteration_result)

            iteration_snapshot = {
                "iteration": iteration,
                "quality": quality_result,
                "consistency": consistency_result,
                "coordinator": coordinator_result,
                "feedback_by_doc": {},
            }
            self.context.quality["previous_results"] = iteration_snapshot

            if not self._should_continue_quality_loop(
                quality_result, coordinator_result
            ):
                self.logger.info("품질 개선 사이클 종료 - 추가 개선 불필요")
                break

            feedback_by_doc = self._aggregate_feedback(
                quality_result, consistency_result, coordinator_result
            )
            iteration_snapshot["feedback_by_doc"] = feedback_by_doc

            if not any(feedback_by_doc.values()):
                self.logger.info("품질 개선 사이클 종료 - 피드백이 없습니다")
                break

            updated_files = self._apply_feedback_to_documents(
                documents,
                feedback_by_doc,
                service_type,
            )
            if not updated_files:
                self.logger.warning("품질 개선 사이클 - 문서 갱신 실패, 루프 종료")
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

        return summary

    def _load_generated_documents(
        self, service_type: ServiceType
    ) -> Dict[str, Dict[str, str]]:
        """현재 출력 디렉토리에서 문서를 읽어옵니다."""

        output_dir = Path(self.context.project.get("output_dir", ""))
        if not output_dir:
            return {}

        documents: Dict[str, Dict[str, str]] = {}
        for agent_name in self.document_order(service_type):
            filename = "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
            file_path = output_dir / filename
            if not file_path.exists():
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                self.agent_logger_factory(agent_name).exception(
                    "문서 로드 실패 | 파일: %s", str(file_path)
                )
                continue

            documents[agent_name] = {"path": str(file_path), "content": content}
        return documents

    def _format_documents_for_review(
        self, documents: Dict[str, Dict[str, str]], service_type: ServiceType
    ) -> str:
        """검토용 요약 문자열을 생성합니다."""

        output_dir = self.context.project.get("output_dir", "")
        lines: List[str] = [f"검토 대상 문서 목록 (output_dir={output_dir}):"]
        for agent_name in self.document_order(service_type):
            doc = documents.get(agent_name)
            if not doc:
                continue

            title = "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
            lines.append(f"- {title}: {doc['path']}")
        return "\n".join(lines)

    def _parse_json_response(self, agent_name: str, response: Any) -> Dict[str, Any]:
        """에이전트 응답을 JSON으로 파싱합니다."""

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

        self.agent_logger_factory(agent_name).warning(
            "JSON 파싱 실패 - 원문을 raw_response로 저장합니다"
        )
        return {"raw_response": text}

    def _should_continue_quality_loop(
        self,
        quality_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> bool:
        """추가 품질 개선 필요 여부를 판단합니다."""

        if not isinstance(quality_result, dict):
            return False

        needs_improvement = bool(quality_result.get("needs_improvement"))
        overall = quality_result.get("overall")
        below_threshold = (
            isinstance(overall, (int, float)) and overall < self.quality_threshold
        )

        coordinator_requires = False
        if isinstance(coordinator_result, dict):
            coordinator_requires = not coordinator_result.get("approved", False)

        return needs_improvement or below_threshold or coordinator_requires

    def _aggregate_feedback(
        self,
        quality_result: Dict[str, Any],
        consistency_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        """품질/일관성/코디네이터 결과에서 문서별 피드백을 수집합니다."""

        feedback_by_doc: Dict[str, List[str]] = {}
        general_notes: List[str] = []
        seen: set = set()

        def _add_feedback(documents: Optional[Any], note: Any, prefix: str):
            if not note:
                return

            if isinstance(note, (dict, list)):
                note_text = json.dumps(note, ensure_ascii=False)
            else:
                note_text = str(note).strip()

            if not note_text:
                return

            labeled_note = f"[{prefix}] {note_text}" if prefix else note_text

            doc_keys: List[str] = []
            if isinstance(documents, list):
                doc_keys = [doc for doc in documents if doc]
            elif documents:
                doc_keys = [documents]

            normalized_docs = [
                doc_key
                for raw in doc_keys
                for doc_key in self._normalize_feedback_documents(raw)
            ]

            if not normalized_docs:
                general_notes.append(labeled_note)
                return

            for doc in normalized_docs:
                key = (doc, labeled_note)
                if key in seen:
                    continue
                seen.add(key)
                feedback_by_doc.setdefault(doc, []).append(labeled_note)

        if isinstance(quality_result, dict):
            for item in quality_result.get("feedback", []) or []:
                if isinstance(item, dict):
                    documents = item.get("documents") or item.get("document")
                    note = item.get("note") or item.get("message") or item.get("detail")
                else:
                    documents = None
                    note = item
                _add_feedback(documents, note, "품질")

        if isinstance(consistency_result, dict):
            for item in consistency_result.get("issues", []) or []:
                if isinstance(item, dict):
                    documents = item.get("documents") or item.get("document")
                    note = item.get("note") or item.get("message") or item.get("detail")
                else:
                    documents = None
                    note = item
                _add_feedback(documents, note, "일관성")

        if isinstance(coordinator_result, dict):
            for item in coordinator_result.get("required_improvements", []) or []:
                if isinstance(item, dict):
                    documents = item.get("documents") or item.get("document")
                    note = item.get("note") or item.get("message") or item.get("detail")
                else:
                    documents = None
                    note = item
                _add_feedback(documents, note, "코디네이터")

        if general_notes:
            for note in general_notes:
                for doc in ["requirements", "design", "tasks", "changes", "openapi"]:
                    key = (doc, note)
                    if key in seen:
                        continue
                    seen.add(key)
                    feedback_by_doc.setdefault(doc, []).append(note)

        return feedback_by_doc

    def _normalize_feedback_documents(self, raw: Any) -> List[str]:
        """피드백 대상 문서 식별자를 정규화합니다."""

        if raw is None:
            return []

        if isinstance(raw, list):
            normalized: List[str] = []
            for value in raw:
                normalized.extend(self._normalize_feedback_documents(value))
            return normalized

        text = str(raw).strip()
        if not text:
            return []

        lowered = text.lower()
        lowered = lowered.replace(".md", "").replace(".json", "")
        lowered = lowered.replace("document", "").replace("doc", "").strip()
        lowered = lowered.replace("섹션", "").strip()

        compact = re.sub(r"[^a-z0-9]", "", lowered)

        alias_map = {
            "requirements": "requirements",
            "requirement": "requirements",
            "req": "requirements",
            "reqs": "requirements",
            "functionalrequirements": "requirements",
            "design": "design",
            "architecture": "design",
            "systemdesign": "design",
            "designdoc": "design",
            "tasks": "tasks",
            "task": "tasks",
            "workplan": "tasks",
            "workbreakdown": "tasks",
            "taskplan": "tasks",
            "changes": "changes",
            "change": "changes",
            "releaseplan": "changes",
            "deploymentplan": "changes",
            "changemanagement": "changes",
            "openapi": "openapi",
            "apispec": "openapi",
            "api": "openapi",
        }

        normalized = alias_map.get(compact) or alias_map.get(lowered)
        return [normalized] if normalized else []

    def _apply_feedback_to_documents(
        self,
        documents: Dict[str, Dict[str, str]],
        feedback_by_doc: Dict[str, List[str]],
        service_type: ServiceType,
    ) -> List[str]:
        """피드백을 바탕으로 문서를 갱신합니다."""

        if not feedback_by_doc:
            return []

        updated_files: List[str] = []
        for agent_name in self.document_order(service_type):
            if agent_name not in documents:
                continue

            document_feedback = feedback_by_doc.get(agent_name, [])
            if not document_feedback:
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                continue

            current_content = documents[agent_name]["content"]
            template_result = self.context.documents.template_results.get(
                agent_name, {}
            )
            required_sections = pair_required_sections(
                template_result.get("required_sections") or []
            )
            improvement_prompt = build_improvement_prompt(
                agent_name,
                current_content,
                document_feedback,
                required_sections,
            )

            if not improvement_prompt:
                continue

            try:
                result = agent(improvement_prompt)
                processed = self.process_agent_result(agent_name, result)
                self.validate_and_record(agent_name, processed)
                save_result = self.save_document(agent_name, processed)
                if save_result:
                    updated_files.append(save_result["file_path"])
                    documents[agent_name]["content"] = processed
                    self.context.documents.previous_contents[agent_name] = processed
            except Exception:
                self.agent_logger_factory(agent_name).exception("피드백 적용 실패")

        return updated_files
