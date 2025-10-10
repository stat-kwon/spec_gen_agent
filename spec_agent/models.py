"""Data models for the spec_agent system."""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class ServiceType(Enum):
    """Service type enumeration."""

    API = "api"
    WEB = "web"


class FRSDocument(BaseModel):
    """FRS document model."""

    title: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class GenerationContext(BaseModel):
    """Context for document generation."""

    frs: FRSDocument
    service_type: ServiceType
    output_dir: Optional[str] = None
    requirements: Optional[str] = None
    design: Optional[str] = None
    tasks: Optional[str] = None
    changes: Optional[str] = None
    openapi: Optional[str] = None


class ValidationResult(BaseModel):
    """Result of document validation."""

    success: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


class GenerationResult(BaseModel):
    """Result of document generation."""

    success: bool
    content: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentState(Enum):
    """Document generation state for Agentic Loop."""

    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    FAILED = "failed"


class QualityMetrics(BaseModel):
    """Quality metrics for document evaluation."""

    completeness: float = Field(default=0.0, ge=0.0, le=100.0)
    consistency: float = Field(default=0.0, ge=0.0, le=100.0)
    clarity: float = Field(default=0.0, ge=0.0, le=100.0)
    technical_accuracy: float = Field(default=0.0, ge=0.0, le=100.0)
    overall: float = Field(default=0.0, ge=0.0, le=100.0)

    def calculate_overall(self) -> float:
        """Calculate weighted overall score."""
        self.overall = (
            self.completeness * 0.3
            + self.consistency * 0.3
            + self.clarity * 0.2
            + self.technical_accuracy * 0.2
        )
        return self.overall


class ValidationFeedback(BaseModel):
    """Feedback from validation and consistency checks."""

    document_type: str
    issues: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)
    severity: str = Field(default="medium")  # low, medium, high
