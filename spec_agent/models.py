"""핵심 데이터 모델."""

from enum import Enum
from typing import Any, Dict

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


