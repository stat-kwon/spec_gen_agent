"""품질 피드백을 적용해 문서를 갱신하는 단계."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from spec_agent.models import ServiceType

from ..context import WorkflowContext
from ..utils.feedback_tracker import FeedbackTracker
from .refinement_executor import RefinementExecutor

AgentCallable = Callable[[Any], Any]
AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
ProcessResultFn = Callable[[str, Any], str]
ValidateTemplateFn = Callable[[str, str], Dict[str, Any]]
SaveDocumentFn = Callable[[str, str], Optional[Dict[str, Any]]]
DocumentOrderFn = Callable[[ServiceType], Sequence[str]]


class QualityFeedbackPhase:
    """품질 평가 결과를 반영해 문서를 재작성합니다."""

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
        feedback_tracker: FeedbackTracker,
    ) -> None:
        self.context = context
        self.agents = agents
        self.logger = logger
        self.agent_logger_factory = agent_logger_factory
        self.document_order = document_order
        self.feedback_tracker = feedback_tracker

        self.refinement_executor = RefinementExecutor(
            context=context,
            agents=agents,
            logger=logger,
            agent_logger_factory=agent_logger_factory,
            document_order=document_order,
            process_agent_result=process_agent_result,
            validate_and_record=validate_and_record,
            save_document=save_document,
            feedback_tracker=feedback_tracker,
        )

    def apply_feedback(
        self,
        documents: Dict[str, Dict[str, str]],
        feedback_by_doc: Dict[str, List[str]],
        service_type: ServiceType,
        iteration: int,
    ) -> Dict[str, Any]:
        """평가 결과를 기반으로 문서를 재작성합니다."""

        if not feedback_by_doc:
            return {
                "filtered_feedback": {},
                "skipped_feedback": {},
                "updated_files": [],
            }

        filtered_feedback, skipped_feedback = self.feedback_tracker.filter_verified(
            feedback_by_doc
        )

        if skipped_feedback:
            self.logger.info(
                "이미 반영된 피드백 %d건을 건너뜀 | 상세: %s",
                sum(len(v) for v in skipped_feedback.values()),
                skipped_feedback,
            )

        if not any(filtered_feedback.values()):
            self.logger.info("적용할 새 피드백이 없어 개선 단계를 종료합니다")
            return {
                "filtered_feedback": filtered_feedback,
                "skipped_feedback": skipped_feedback,
                "updated_files": [],
            }

        updated_files = self.refinement_executor.execute(
            documents,
            filtered_feedback,
            service_type,
            iteration,
        )

        if not updated_files:
            self.logger.warning("개선 적용 실패 - 문서 저장 결과가 없습니다")

        return {
            "filtered_feedback": filtered_feedback,
            "skipped_feedback": skipped_feedback,
            "updated_files": updated_files,
        }
