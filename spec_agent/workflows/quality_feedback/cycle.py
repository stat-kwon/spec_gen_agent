"""품질 평가 루프."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from spec_agent.models import ServiceType

from ..context import WorkflowContext
from ..prompts import (
    build_consistency_review_prompt,
    build_coordinator_prompt,
    build_quality_review_prompt,
)

AgentCallable = Callable[[Any], Any]
AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
DocumentOrderFn = Callable[[ServiceType], List[str]]


@dataclass
class QualityFeedbackResult:
    """품질 평가 반복의 결과."""

    iteration: int
    quality: Dict[str, Any]
    consistency: Dict[str, Any]
    coordinator: Dict[str, Any]
    review_payload: str
    feedback_by_doc: Dict[str, List[str]]
    documents: Dict[str, Dict[str, str]]


class QualityFeedbackLoop:
    """품질·일관성 평가와 코디네이터 피드백을 수행합니다."""

    def __init__(
        self,
        context: WorkflowContext,
        agents: Dict[str, AgentCallable],
        agent_logger_factory: AgentLoggerFactory,
        document_order: DocumentOrderFn,
        logger: logging.LoggerAdapter,
    ) -> None:
        self.context = context
        self.agents = agents
        self.agent_logger_factory = agent_logger_factory
        self.document_order = document_order
        self.logger = logger

    def run_iteration(
        self,
        service_type: ServiceType,
        iteration: int,
        verified_feedback: Optional[Dict[str, List[str]]] = None,
    ) -> Optional[QualityFeedbackResult]:
        """평가 에이전트를 실행해 피드백을 수집합니다."""

        documents = self._load_generated_documents(service_type)
        if not documents:
            self.logger.warning("품질 평가 루프 중단 - 검토할 문서가 없습니다")
            return None

        review_payload = self._format_documents_for_review(documents, service_type)
        output_dir = self.context.project.get("output_dir", "")

        quality_prompt = build_quality_review_prompt(output_dir, review_payload)
        quality_raw = self.agents["quality_assessor"](quality_prompt)
        quality_result = self._parse_json_response("quality_assessor", quality_raw)

        consistency_prompt = build_consistency_review_prompt(output_dir, review_payload)
        consistency_raw = self.agents["consistency_checker"](consistency_prompt)
        consistency_result = self._parse_json_response(
            "consistency_checker", consistency_raw
        )

        coordinator_prompt = build_coordinator_prompt(
            output_dir,
            review_payload,
            quality_result,
            consistency_result,
            verified_feedback,
        )
        coordinator_raw = self.agents["coordinator"](coordinator_prompt)
        coordinator_result = self._parse_json_response(
            "coordinator", coordinator_raw
        )

        feedback_by_doc = self._aggregate_feedback(
            quality_result,
            consistency_result,
            coordinator_result,
        )
        coordinator_feedback = self._collect_coordinator_feedback(coordinator_result)
        for doc, items in coordinator_feedback.items():
            feedback_by_doc.setdefault(doc, []).extend(items)
        feedback_by_doc = {
            doc: list(dict.fromkeys(item for item in items if item))
            for doc, items in feedback_by_doc.items()
        }

        return QualityFeedbackResult(
            iteration=iteration,
            quality=quality_result,
            consistency=consistency_result,
            coordinator=coordinator_result,
            review_payload=review_payload,
            feedback_by_doc=feedback_by_doc,
            documents=documents,
        )

    # ------------------------------------------------------------------ #
    # 내부 유틸리티
    # ------------------------------------------------------------------ #

    def _load_generated_documents(
        self, service_type: ServiceType
    ) -> Dict[str, Dict[str, str]]:
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

    def _aggregate_feedback(
        self,
        quality_result: Dict[str, Any],
        consistency_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        feedback_by_doc: Dict[str, List[str]] = {}
        seen: set[tuple[str, str]] = set()
        general_notes: List[str] = []

        def _add_feedback(
            documents: Optional[Any],
            note: Optional[Any],
            prefix: Optional[str],
        ) -> None:
            if not note:
                return

            if isinstance(note, (dict, list)):
                note_text = json.dumps(note, ensure_ascii=False)
            else:
                note_text = str(note).strip()

            if not note_text:
                return

            labeled_note = f"[{prefix}] {note_text}" if prefix else note_text

            if isinstance(documents, list):
                doc_keys = [doc for doc in documents if doc]
            elif documents:
                doc_keys = [documents]
            else:
                doc_keys = []

            normalized_docs = [
                doc_key
                for raw in doc_keys
                for doc_key in self._normalize_document_labels(raw)
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

    def _collect_coordinator_feedback(
        self, coordinator_result: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        feedback: Dict[str, List[str]] = {}
        if not isinstance(coordinator_result, dict):
            return feedback

        for item in coordinator_result.get("required_improvements", []) or []:
            if isinstance(item, dict):
                documents = item.get("documents") or item.get("document")
                note = item.get("note") or item.get("message") or item.get("detail")
            else:
                documents = None
                note = item

            if not note:
                continue

            if documents is None:
                targets = []
            elif isinstance(documents, (list, tuple, set)):
                targets = list(documents)
            else:
                targets = [documents]

            normalized_targets = [
                doc
                for raw in targets
                for doc in self._normalize_document_labels(raw)
            ]

            if not normalized_targets:
                normalized_targets = ["general"]

            for doc in normalized_targets:
                feedback.setdefault(doc, []).append(str(note).strip())

        return feedback

    def _normalize_document_labels(self, raw: Any) -> List[str]:
        if raw is None:
            return []

        if isinstance(raw, list):
            normalized: List[str] = []
            for value in raw:
                normalized.extend(self._normalize_document_labels(value))
            return normalized

        text = str(raw).strip()
        if not text:
            return []

        lowered = text.lower()
        lowered = lowered.replace(".md", "").replace(".json", "")
        lowered = lowered.replace("document", "").replace("doc", "").strip()
        lowered = lowered.replace("섹션", "").strip()

        import re

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
