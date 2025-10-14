"""생성된 명세서를 위한 검증 도구들."""

from __future__ import annotations

import json
import logging
from typing import Dict, Any
from strands import tool

from spec_agent.utils.logging import get_session_logger


LOGGER = logging.getLogger("spec_agent.tools.validation")


def _get_logger(
    session_id: str | None = None,
) -> logging.LoggerAdapter | logging.Logger:
    if session_id:
        return get_session_logger("tools.validation", session_id)
    return LOGGER


@tool
def validate_openapi_spec(
    openapi_content: str,
    *,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    OpenAPI 3.1 명세서를 검증합니다.

    Args:
        openapi_content: OpenAPI 명세서를 담은 JSON 문자열

    Returns:
        검증 결과를 담은 딕셔너리
    """
    logger = _get_logger(session_id)
    logger.info("OpenAPI 검증 시작")

    try:
        # Parse JSON
        try:
            spec = json.loads(openapi_content)
        except json.JSONDecodeError as e:
            logger.error("OpenAPI JSON 파싱 실패 | 오류=%s", e.msg)
            return {"success": False, "error": f"Invalid JSON: {str(e)}"}

        # Basic OpenAPI 3.1 schema validation
        required_fields = ["openapi", "info", "paths"]
        missing_fields = []

        for field in required_fields:
            if field not in spec:
                missing_fields.append(field)

        if missing_fields:
            logger.warning("OpenAPI 필수 필드 누락 | 필드=%s", missing_fields)
            return {
                "success": False,
                "error": f"Missing required fields: {missing_fields}",
            }

        # Check OpenAPI version
        openapi_version = spec.get("openapi", "")
        if not openapi_version.startswith("3.1"):
            logger.warning("OpenAPI 버전 불일치 | 버전=%s", openapi_version)
            return {
                "success": False,
                "error": f"Expected OpenAPI 3.1.x, got: {openapi_version}",
            }

        # Validate info section
        info = spec.get("info", {})
        if not info.get("title") or not info.get("version"):
            logger.warning("OpenAPI info 섹션 누락")
            return {
                "success": False,
                "error": "Info section must contain title and version",
            }

        # Count API elements
        paths_count = len(spec.get("paths", {}))
        components_count = len(spec.get("components", {}).get("schemas", {}))

        result = {
            "success": True,
            "openapi_version": openapi_version,
            "api_title": info.get("title"),
            "api_version": info.get("version"),
            "paths_count": paths_count,
            "components_count": components_count,
            "validation_summary": f"Valid OpenAPI 3.1 spec with {paths_count} paths and {components_count} components",
        }
        logger.info(
            "OpenAPI 검증 성공 | 경로=%d | 컴포넌트=%d",
            paths_count,
            components_count,
        )
        return result

    except Exception as e:
        logger.exception("OpenAPI 검증 실패")
        return {"success": False, "error": f"OpenAPI validation failed: {str(e)}"}
