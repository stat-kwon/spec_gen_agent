"""spec_agent 시스템용 데이터 모델."""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class ServiceType(Enum):
    """서비스 타입 열거형."""

    API = "api"
    WEB = "web"


class FRSDocument(BaseModel):
    """FRS 문서 모델."""

    title: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GenerationContext(BaseModel):
    """문서 생성을 위한 컨텍스트."""

    frs: FRSDocument
    service_type: ServiceType
    output_dir: Optional[str] = None
    requirements: Optional[str] = None
    design: Optional[str] = None
    tasks: Optional[str] = None
    changes: Optional[str] = None
    openapi: Optional[str] = None


class ValidationResult(BaseModel):
    """문서 검증 결과."""

    success: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


class GenerationResult(BaseModel):
    """문서 생성 결과."""

    success: bool
    content: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentState(Enum):
    """Agentic Loop을 위한 문서 생성 상태."""

    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    FAILED = "failed"


class QualityMetrics(BaseModel):
    """문서 평가를 위한 품질 메트릭."""

    completeness: float = Field(default=0.0, ge=0.0, le=100.0)
    consistency: float = Field(default=0.0, ge=0.0, le=100.0)
    clarity: float = Field(default=0.0, ge=0.0, le=100.0)
    technical_accuracy: float = Field(default=0.0, ge=0.0, le=100.0)
    overall: float = Field(default=0.0, ge=0.0, le=100.0)

    def calculate_overall(self) -> float:
        """가중 전체 점수 계산."""
        self.overall = (
            self.completeness * 0.3
            + self.consistency * 0.3
            + self.clarity * 0.2
            + self.technical_accuracy * 0.2
        )
        return self.overall


class ValidationFeedback(BaseModel):
    """검증 및 일관성 검사에서 나온 피드백."""

    document_type: str
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    severity: str = Field(default="medium")  # low, medium, high
