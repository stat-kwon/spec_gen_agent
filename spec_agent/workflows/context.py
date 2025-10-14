from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DocumentContext:
    """워크플로우 문서 상태를 보관합니다."""

    previous_contents: Dict[str, str] = field(default_factory=dict)
    template_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class WorkflowContext:
    """워크플로우 실행 전반의 컨텍스트를 유지합니다."""

    project: Dict[str, Any] = field(default_factory=dict)
    documents: DocumentContext = field(default_factory=DocumentContext)
    quality: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """사전 형태로 컨텍스트를 반환합니다."""

        return {
            "project": self.project,
            "documents": {
                "previous_contents": self.documents.previous_contents,
                "template_results": self.documents.template_results,
            },
            "quality": self.quality,
            "metrics": self.metrics,
        }
