"""피드백을 기반으로 문서를 재생성하는 실행기."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from spec_agent.models import ServiceType

from ..prompts import build_improvement_prompt
from ..utils.feedback_tracker import FeedbackTracker
from ..utils.prompt_helpers import pair_required_sections

AgentCallable = Callable[[Any], Any]
AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
ProcessResultFn = Callable[[str, Any], str]
ValidateTemplateFn = Callable[[str, str], Dict[str, Any]]
SaveDocumentFn = Callable[[str, str], Optional[Dict[str, Any]]]


class RefinementExecutor:
    """coordinator 개선 지시를 기반으로 문서를 재생성합니다."""

    def __init__(
        self,
        context,
        agents: Dict[str, AgentCallable],
        logger: logging.LoggerAdapter,
        agent_logger_factory: AgentLoggerFactory,
        document_order: Callable[[ServiceType], List[str]],
        process_agent_result: ProcessResultFn,
        validate_and_record: ValidateTemplateFn,
        save_document: SaveDocumentFn,
        feedback_tracker: FeedbackTracker,
    ) -> None:
        self.context = context
        self.agents = agents
        self.logger = logger
        self.agent_logger_factory = agent_logger_factory
        self.document_order = document_order
        self.process_agent_result = process_agent_result
        self.validate_and_record = validate_and_record
        self.save_document = save_document
        self.feedback_tracker = feedback_tracker

    def execute(
        self,
        documents: Dict[str, Dict[str, str]],
        document_feedback: Dict[str, List[str]],
        service_type: ServiceType,
        iteration: int,
    ) -> List[str]:
        """문서별 개선 지시를 반영합니다."""

        if not document_feedback:
            return []

        updated_files: List[str] = []

        for agent_name in self.document_order(service_type):
            improvements = document_feedback.get(agent_name)
            if not improvements:
                continue

            document_info = documents.get(agent_name)
            if not document_info:
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                continue

            agent_logger = self.agent_logger_factory(agent_name)
            agent_logger.info(
                "개선 지시 적용 시작 | 항목 %d개",
                len(improvements),
            )

            file_path_str = document_info["path"]
            file_path = Path(file_path_str)
            try:
                current_content = file_path.read_text(encoding="utf-8")
                agent_logger.info(
                    "기존 문서 로드 완료 | 파일: %s | 문자 수: %d",
                    file_path_str,
                    len(current_content),
                )
            except Exception:
                agent_logger.exception("최신 문서 로드 실패 | 경로: %s", file_path)
                current_content = document_info["content"]
                agent_logger.warning(
                    "컨텍스트 저장본 사용 | 파일: %s | 문자 수: %d",
                    file_path_str,
                    len(current_content),
                )

            unique_improvements = list(dict.fromkeys(improvements))
            if not unique_improvements:
                agent_logger.info("중복 제거 후 적용할 개선 지시가 없습니다")
                continue

            template_info = {}
            if getattr(self.context, "documents", None):
                template_info = (
                    self.context.documents.template_results.get(agent_name, {}) or {}
                )
            required_sections = pair_required_sections(
                template_info.get("required_sections") or []
            )
            prompt = build_improvement_prompt(
                agent_name,
                current_content,
                unique_improvements,
                required_sections,
                file_path_str,
            )

            if not prompt:
                agent_logger.warning("개선 프롬프트 생성 실패 - 건너뜀")
                continue

            agent_logger.debug(
                "개선 프롬프트 준비 완료 | 파일: %s | 개선 항목 수: %d",
                file_path_str,
                len(unique_improvements),
            )

            try:
                result = agent(prompt)
                processed = self.process_agent_result(agent_name, result)
                if processed == current_content:
                    agent_logger.warning(
                        "개선 결과가 기존 문서와 동일해 저장을 건너뜁니다 | 파일: %s",
                        file_path_str,
                    )
                    continue
                self.validate_and_record(agent_name, processed)
                save_result = self.save_document(agent_name, processed)
                if save_result:
                    content_hash = hashlib.md5(
                        processed.encode("utf-8")
                    ).hexdigest()
                    self.feedback_tracker.mark_pending(
                        agent_name,
                        unique_improvements,
                        iteration,
                        content_hash,
                    )
                    updated_files.append(save_result["file_path"])
                    document_info["content"] = processed
                    if getattr(self.context, "documents", None):
                        self.context.documents.previous_contents[agent_name] = processed
                    agent_logger.info(
                        "개선 적용 완료 | 파일: %s",
                        save_result["file_path"],
                    )
                else:
                    agent_logger.error("개선된 문서 저장 실패")
            except Exception:
                agent_logger.exception("개선 적용 중 오류 발생")

        return updated_files
