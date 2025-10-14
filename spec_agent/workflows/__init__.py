from typing import Dict, Optional, Type

from spec_agent.config import Config

from .sequential import SequentialWorkflow


WorkflowType = Type[SequentialWorkflow]

_WORKFLOW_REGISTRY: Dict[str, WorkflowType] = {
    "sequential": SequentialWorkflow,
}


def get_workflow(
    name: str = "sequential",
    config: Optional[Config] = None,
) -> SequentialWorkflow:
    """워크플로우를 이름으로 조회합니다."""

    try:
        workflow_cls = _WORKFLOW_REGISTRY[name]
    except KeyError as exc:
        available = ", ".join(sorted(_WORKFLOW_REGISTRY))
        raise ValueError(
            f"알 수 없는 워크플로우: {name!r} (사용 가능: {available})"
        ) from exc

    return workflow_cls(config=config)


SpecificationWorkflow = SequentialWorkflow

__all__ = [
    "get_workflow",
    "SequentialWorkflow",
    "SpecificationWorkflow",
]
