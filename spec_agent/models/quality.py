"""품질 평가를 위한 Pydantic 모델들."""

from typing import List, Optional
from pydantic import BaseModel, Field


class QualityReport(BaseModel):
    """문서 품질 평가 보고서."""
    
    completeness: int = Field(
        ge=0, le=100, 
        description="문서 완성도 점수 (0-100)"
    )
    consistency: int = Field(
        ge=0, le=100,
        description="일관성 점수 (0-100)"
    )
    clarity: int = Field(
        ge=0, le=100,
        description="명확성 점수 (0-100)"
    )
    technical: int = Field(
        ge=0, le=100,
        description="기술적 정확성 점수 (0-100)"
    )
    overall: int = Field(
        ge=0, le=100,
        description="전체 점수 (0-100)"
    )
    feedback: List[str] = Field(
        default=[],
        description="개선 피드백 목록"
    )
    
    class Config:
        """Pydantic 설정."""
        json_schema_extra = {
            "example": {
                "completeness": 85,
                "consistency": 90,
                "clarity": 80,
                "technical": 88,
                "overall": 86,
                "feedback": [
                    "요구사항 ID 체계 개선 필요",
                    "시퀀스 다이어그램에 오류 처리 추가 필요"
                ]
            }
        }


class ConsistencyReport(BaseModel):
    """문서 간 일관성 검증 보고서."""
    
    issues: List[str] = Field(
        default=[],
        description="발견된 일관성 이슈 목록"
    )
    severity: str = Field(
        description="전체 심각도 (low/medium/high)"
    )
    cross_references: int = Field(
        ge=0,
        description="교차 참조 누락 개수"
    )
    naming_conflicts: int = Field(
        ge=0,
        description="명명 충돌 개수"
    )
    
    class Config:
        """Pydantic 설정."""
        json_schema_extra = {
            "example": {
                "issues": [
                    "설계 문서에서 요구사항 REQ-003 참조 누락",
                    "API 명세와 설계의 엔드포인트 이름 불일치"
                ],
                "severity": "medium",
                "cross_references": 2,
                "naming_conflicts": 1
            }
        }


class ApprovalDecision(BaseModel):
    """최종 승인 결정."""
    
    approved: bool = Field(
        description="승인 여부"
    )
    reason: str = Field(
        description="승인 또는 거부 사유"
    )
    required_improvements: List[str] = Field(
        default=[],
        description="필요한 개선사항 목록"
    )
    confidence: int = Field(
        ge=0, le=100,
        description="결정에 대한 신뢰도 (0-100)"
    )
    
    class Config:
        """Pydantic 설정."""
        json_schema_extra = {
            "example": {
                "approved": False,
                "reason": "전체 품질 점수가 기준(85점) 미달",
                "required_improvements": [
                    "요구사항 문서 상세화",
                    "시퀀스 다이어그램 오류 처리 추가",
                    "API 명세 일관성 개선"
                ],
                "confidence": 92
            }
        }


class DocumentMetrics(BaseModel):
    """문서 메트릭 정보."""
    
    document_type: str = Field(description="문서 유형")
    word_count: int = Field(ge=0, description="단어 수")
    section_count: int = Field(ge=0, description="섹션 수")
    requirement_count: Optional[int] = Field(None, description="요구사항 수 (해당시)")
    diagram_count: Optional[int] = Field(None, description="다이어그램 수 (해당시)")
    
    class Config:
        """Pydantic 설정."""
        json_schema_extra = {
            "example": {
                "document_type": "requirements",
                "word_count": 1250,
                "section_count": 6,
                "requirement_count": 15,
                "diagram_count": None
            }
        }


class WorkflowState(BaseModel):
    """워크플로우 상태 정보."""
    
    session_id: str = Field(description="세션 ID")
    current_iteration: int = Field(ge=1, le=3, description="현재 반복 횟수")
    max_iterations: int = Field(default=3, description="최대 반복 횟수")
    documents_generated: List[str] = Field(default=[], description="생성된 문서 목록")
    quality_threshold: int = Field(default=85, description="품질 임계값")
    
    class Config:
        """Pydantic 설정."""
        json_schema_extra = {
            "example": {
                "session_id": "spec_gen_20241010_143022",
                "current_iteration": 1,
                "max_iterations": 3,
                "documents_generated": ["requirements", "design", "tasks"],
                "quality_threshold": 85
            }
        }