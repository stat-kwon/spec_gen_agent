"""spec_agent 시스템용 데이터 모델."""

from typing import Dict, Any
from pydantic import BaseModel, Field


class FRSDocument(BaseModel):
    """FRS 문서 모델."""

    title: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
