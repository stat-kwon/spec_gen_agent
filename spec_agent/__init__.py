"""
Strands Agent SDK 기반 명세서 생성 시스템.

이 패키지는 Strands Agent SDK 프레임워크를 사용하여 FRS(Functional Requirements Specification)
마크다운 파일로부터 서비스 문서를 생성하는 멀티 에이전트 시스템을 제공합니다.
"""

from .workflow import SpecificationWorkflow
from .models import ServiceType

__version__ = "2.0.0"
__all__ = ["SpecificationWorkflow", "ServiceType"]
