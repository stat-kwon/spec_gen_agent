"""생성된 명세서를 위한 검증 도구들."""

from __future__ import annotations

import json
import logging
import re
from typing import Dict, Any, List

from jsonschema import ValidationError, validate
from strands import tool

from ..logging_utils import get_session_logger


LOGGER = logging.getLogger("spec_agent.tools.validation")


def _get_logger(session_id: str | None = None) -> logging.LoggerAdapter | logging.Logger:
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


@tool
def validate_markdown_content(
    content: str,
    document_type: str,
    *,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    마크다운 컨텐츠의 구조와 품질을 검증합니다.

    Args:
        content: 검증할 마크다운 컨텐츠
        document_type: 문서 타입 (requirements, design, tasks, changes)

    Returns:
        검증 결과를 담은 딕셔너리
    """
    logger = _get_logger(session_id)
    logger.info("마크다운 내용 검증 시작 | 타입=%s", document_type)

    try:
        issues = []
        warnings = []
        metrics = {}

        # Basic content checks
        if not content.strip():
            logger.warning("문서 내용 없음")
            issues.append("Document is empty")
            return {
                "success": False,
                "issues": issues,
                "warnings": warnings,
                "metrics": metrics,
            }

        # Check for proper heading structure
        headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        if not headings:
            issues.append("No headings found")
            logger.warning("헤딩 없음")
        else:
            # Check heading hierarchy
            prev_level = 0
            for heading_marks, heading_text in headings:
                current_level = len(heading_marks)
                if current_level > prev_level + 1:
                    warnings.append(f"Heading level jump: '{heading_text}'")
                prev_level = current_level

        # Document type specific validations
        if document_type == "requirements":
            # Check for requirements identifiers
            req_ids = re.findall(r"REQ-\d+", content)
            if not req_ids:
                logger.warning("요구사항 ID 없음")
                warnings.append("No requirement identifiers (REQ-XXX) found")
            metrics["requirements_count"] = len(req_ids)

        elif document_type == "design":
            # Check for sequence diagrams
            if (
                "mermaid" not in content.lower()
                and "sequencediagram" not in content.lower()
            ):
                logger.warning("시퀀스 다이어그램 없음")
                warnings.append("No sequence diagram found")

        elif document_type == "tasks":
            # Check for task tables
            table_count = len(re.findall(r"\|.*\|", content))
            if table_count < 3:  # Header + separator + at least one row
                logger.warning("태스크 테이블 부족 | 행=%d", table_count)
                warnings.append("Task tables appear to be missing or incomplete")
            metrics["table_rows"] = table_count

        elif document_type == "changes":
            # Check for version information
            if not re.search(r"version|v\d+\.\d+", content, re.IGNORECASE):
                logger.warning("버전 정보 없음")
                warnings.append("No version information found")

        # General quality checks
        word_count = len(content.split())
        line_count = len(content.splitlines())

        if word_count < 100:
            logger.warning("문서 길이 짧음 | 단어수=%d", word_count)
            warnings.append(f"Document seems short ({word_count} words)")

        # Check for TODO/FIXME markers
        todo_markers = re.findall(r"TODO|FIXME|TBD|XXX", content, re.IGNORECASE)
        if todo_markers:
            logger.warning("TODO/FIXME 발견 | 개수=%d", len(todo_markers))
            warnings.append(f"Found {len(todo_markers)} TODO/FIXME markers")

        metrics.update(
            {
                "word_count": word_count,
                "line_count": line_count,
                "heading_count": len(headings),
                "todo_count": len(todo_markers),
            }
        )

        result = {
            "success": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "metrics": metrics,
            "document_type": document_type,
        }
        logger.info(
            "마크다운 내용 검증 완료 | 이슈=%d | 경고=%d",
            len(issues),
            len(warnings),
        )
        return result

    except Exception as e:
        logger.exception("마크다운 내용 검증 실패")
        return {"success": False, "error": f"Markdown validation failed: {str(e)}"}
