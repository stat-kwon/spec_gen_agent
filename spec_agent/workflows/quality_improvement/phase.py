"""품질 개선 단계를 조율하는 모듈."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Sequence, Tuple

from spec_agent.models import ServiceType

from ..context import WorkflowContext
from ..quality_feedback.cycle import QualityFeedbackLoop, QualityFeedbackResult
from ..utils.feedback_tracker import FeedbackTracker

if TYPE_CHECKING:
    from ..quality_feedback.phase import QualityFeedbackPhase

AgentCallable = Callable[[Any], Any]
AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
DocumentOrderFn = Callable[[ServiceType], Sequence[str]]


class QualityImprovementPhase:
    """품질/일관성 평가와 종료 여부 판단을 담당합니다."""

    def __init__(
        self,
        context: WorkflowContext,
        agents: Dict[str, AgentCallable],
        logger: logging.LoggerAdapter,
        agent_logger_factory: AgentLoggerFactory,
        document_order: DocumentOrderFn,
        feedback_tracker: FeedbackTracker,
        max_iterations: int,
        quality_threshold: float,
    ) -> None:
        self.context = context
        self.agents = agents
        self.logger = logger
        self.agent_logger_factory = agent_logger_factory
        self.document_order = document_order
        self.feedback_tracker = feedback_tracker
        self.max_iterations = max(1, max_iterations)
        self.quality_threshold = quality_threshold

        self.feedback_loop = QualityFeedbackLoop(
            context=context,
            agents=agents,
            agent_logger_factory=agent_logger_factory,
            document_order=document_order,
            logger=logger,
        )

    def reset(self) -> None:
        """누적된 상태를 초기화합니다."""

        self.context.quality.pop("previous_results", None)

    def evaluate_iteration(
        self,
        service_type: ServiceType,
        iteration: int,
    ) -> Tuple[Optional[QualityFeedbackResult], bool]:
        """단일 평가 반복을 수행하고 종료 여부를 반환합니다."""

        verified_feedback = self.feedback_tracker.verified_feedback()
        if verified_feedback:
            self.context.quality["verified_feedback"] = verified_feedback
        else:
            self.context.quality.pop("verified_feedback", None)

        iteration_result = self.feedback_loop.run_iteration(
            service_type,
            iteration,
            verified_feedback=verified_feedback,
        )

        if iteration_result is None:
            return None, False

        iteration_snapshot = {
            "iteration": iteration,
            "quality": iteration_result.quality,
            "consistency": iteration_result.consistency,
            "coordinator": iteration_result.coordinator,
            "feedback_by_doc": iteration_result.feedback_by_doc.copy(),
        }
        self.context.quality["previous_results"] = iteration_snapshot

        self.feedback_tracker.update_with_feedback(iteration_result.feedback_by_doc)

        should_continue = self._should_continue(
            iteration_result.quality,
            iteration_result.coordinator,
        )

        return iteration_result, should_continue

    async def execute(
        self,
        service_type: ServiceType,
        feedback_phase: "QualityFeedbackPhase",
    ) -> Dict[str, Any]:
        """품질 평가와 개선을 연속 실행합니다."""

        self.reset()

        cycle_results: List[Dict[str, Any]] = []
        improvement_applied = False
        cumulative_updated_files: List[str] = []

        iteration_limit = getattr(self, "max_iterations", 1)

        for iteration in range(1, iteration_limit + 1):
            iteration_result, should_continue = self.evaluate_iteration(
                service_type, iteration
            )
            if iteration_result is None:
                break

            cycle_results.append(
                {
                    "iteration": iteration,
                    "quality": iteration_result.quality,
                    "consistency": iteration_result.consistency,
                    "coordinator": iteration_result.coordinator,
                }
            )

            if not should_continue:
                break

            feedback_outcome = feedback_phase.apply_feedback(
                documents=iteration_result.documents,
                feedback_by_doc=iteration_result.feedback_by_doc,
                service_type=service_type,
                iteration=iteration,
            )

            updated_files = feedback_outcome.get("updated_files", [])
            iteration_snapshot = self.context.quality.get("previous_results", {})
            iteration_snapshot["filtered_feedback"] = feedback_outcome.get(
                "filtered_feedback", {}
            )
            skipped = feedback_outcome.get("skipped_feedback", {})
            if skipped:
                iteration_snapshot["skipped_feedback"] = skipped
            iteration_snapshot["applied_files"] = updated_files
            self.context.quality["previous_results"] = iteration_snapshot
            if not updated_files:
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

    def _should_continue(
        self,
        quality_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> bool:
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

    # ------------------------------------------------------------------ #
    # 테스트 및 호환성용 유틸리티 래퍼
    # ------------------------------------------------------------------ #

    def _parse_json_response(self, agent_name: str, response: Any) -> Dict[str, Any]:
        return self.feedback_loop._parse_json_response(agent_name, response)

    def _aggregate_feedback(
        self,
        quality_result: Dict[str, Any],
        consistency_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> Dict[str, List[str]]:
        return self.feedback_loop._aggregate_feedback(
            quality_result,
            consistency_result,
            coordinator_result,
        )

    def _collect_coordinator_feedback(
        self, coordinator_result: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        return self.feedback_loop._collect_coordinator_feedback(coordinator_result)

    def _normalize_document_labels(self, raw: Any) -> List[str]:
        return self.feedback_loop._normalize_document_labels(raw)

    def _load_generated_documents(
        self, service_type: ServiceType
    ) -> Dict[str, Dict[str, str]]:
        return self.feedback_loop._load_generated_documents(service_type)

    def _format_documents_for_review(
        self, documents: Dict[str, Dict[str, str]], service_type: ServiceType
    ) -> str:
        return self.feedback_loop._format_documents_for_review(documents, service_type)
