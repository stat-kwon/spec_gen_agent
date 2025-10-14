"""FRS 문서 로딩 및 처리 도구들."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Any

from strands import tool

from spec_agent.utils.logging import get_session_logger
from ..models import FRSDocument


LOGGER = logging.getLogger("spec_agent.tools.frs")


def _get_logger(
    session_id: str | None = None,
) -> logging.LoggerAdapter | logging.Logger:
    if session_id:
        return get_session_logger("tools.frs", session_id)
    return LOGGER


@tool
def load_frs_document(
    frs_path: str = "specs/FRS-1.md",
    *,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    FRS 마크다운 문서를 로드하고 파싱합니다.

    Args:
        frs_path: FRS 마크다운 파일 경로 (기본값: specs/FRS-1.md)

    Returns:
        FRS 문서 데이터를 담은 딕셔너리
    """
    logger = _get_logger(session_id)
    logger.info("FRS 로드 시도 | 경로=%s", frs_path)

    try:
        # 현재 작업 디렉토리를 기준으로 경로 해석
        path = Path(frs_path)

        # 상대 경로인 경우 현재 작업 디렉토리 기준으로 절대 경로로 변환
        if not path.is_absolute():
            path = Path.cwd() / path

        # 파일 존재 여부 확인 및 디버깅 정보 포함
        if not path.exists():
            # 대안 경로들 시도
            alternative_paths = [
                Path.cwd() / "specs/FRS-1.md",
                Path.cwd() / "spec_agent" / "specs/FRS-1.md",
                Path(frs_path),
            ]

            for alt_path in alternative_paths:
                if alt_path.exists():
                    path = alt_path
                    break
            else:
                logger.error("FRS 파일 찾을 수 없음 | 경로=%s", path)
                raise FileNotFoundError(
                    f"FRS file not found at {path}. Tried: {[str(p) for p in alternative_paths]}"
                )

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract title from first heading
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else path.stem

        frs_doc = FRSDocument(
            title=title,
            content=content,
            metadata={
                "file_path": str(path),
                "file_size": len(content),
                "lines": len(content.splitlines()),
            },
        )

        result = {
            "success": True,
            "frs": frs_doc.model_dump(),
            "content": content,
            "title": title,
            "debug_info": f"Successfully loaded from: {path}",
        }
        logger.info("FRS 로드 성공 | 제목=%s", title)
        return result

    except Exception as e:
        logger.exception("FRS 로드 실패")
        return {
            "success": False,
            "error": f"Failed to load FRS document: {str(e)}",
            "attempted_path": str(path) if "path" in locals() else frs_path,
        }


@tool
def extract_frs_metadata(
    frs_content: str,
    *,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    FRS 컨텐츠에서 메타데이터를 추출합니다.

    Args:
        frs_content: 원시 FRS 마크다운 컨텐츠

    Returns:
        추출된 메타데이터를 담은 딕셔너리
    """
    logger = _get_logger(session_id)
    logger.info("FRS 메타데이터 추출 시작")

    try:
        metadata = {}

        # Extract sections
        sections = re.findall(r"^##\s+(.+)$", frs_content, re.MULTILINE)
        metadata["sections"] = sections

        # Extract requirements count
        requirements_match = re.findall(r"REQ-\d+", frs_content)
        metadata["requirements_count"] = len(requirements_match)

        # Extract service mentions
        service_indicators = []
        if re.search(r"\bAPI\b|\bREST\b|\bendpoint\b", frs_content, re.IGNORECASE):
            service_indicators.append("api")
        if re.search(
            r"\bweb\b|\bUI\b|\bfrontend\b|\bpage\b", frs_content, re.IGNORECASE
        ):
            service_indicators.append("web")

        metadata["suggested_service_types"] = service_indicators

        # Extract complexity indicators
        complexity_score = 0
        complexity_score += len(
            re.findall(r"\bintegration\b|\bexternal\b", frs_content, re.IGNORECASE)
        )
        complexity_score += len(
            re.findall(
                r"\bauthentication\b|\bauthorization\b", frs_content, re.IGNORECASE
            )
        )
        complexity_score += len(
            re.findall(r"\bdatabase\b|\bstorage\b", frs_content, re.IGNORECASE)
        )

        metadata["complexity_score"] = complexity_score
        metadata["complexity_level"] = (
            "high"
            if complexity_score > 5
            else "medium" if complexity_score > 2 else "low"
        )

        logger.info(
            "FRS 메타데이터 추출 완료 | 섹션=%d | 요구사항=%d",
            len(sections),
            metadata["requirements_count"],
        )
        return {"success": True, "metadata": metadata}

    except Exception as e:
        logger.exception("FRS 메타데이터 추출 실패")
        return {"success": False, "error": f"Failed to extract FRS metadata: {str(e)}"}
