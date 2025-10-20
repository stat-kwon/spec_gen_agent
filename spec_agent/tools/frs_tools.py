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
        metadata: Dict[str, Any] = {}

        def _extract_section_block(title: str) -> str:
            pattern = rf"^##\s+{re.escape(title)}\s*\n(.*?)(?=^##\s+|\Z)"
            match = re.search(pattern, frs_content, re.MULTILINE | re.DOTALL)
            return match.group(1).strip() if match else ""

        def _extract_subsection_block(section_text: str, subheading: str) -> str:
            pattern = rf"^###\s+{re.escape(subheading)}\s*\n(.*?)(?=^###\s+|\Z)"
            match = re.search(pattern, section_text, re.MULTILINE | re.DOTALL)
            return match.group(1).strip() if match else ""

        def _extract_bullets(text: str) -> list[str]:
            return [re.sub(r"^[-*]\s*", "", line.strip()) for line in text.splitlines() if line.strip().startswith(("-", "*"))]

        # Title
        title_match = re.search(r"^#\s+(.+)$", frs_content, re.MULTILINE)
        metadata["title"] = title_match.group(1).strip() if title_match else ""

        # Meta fields from header
        branch_match = re.search(r"\*\*Feature Branch\*\*:\s*`([^`]+)`", frs_content)
        created_match = re.search(r"\*\*Created\*\*:\s*([^\n]+)", frs_content)
        status_match = re.search(r"\*\*Status\*\*:\s*([^\n]+)", frs_content)
        input_match = re.search(r"\*\*Input\*\*:\s*([^\n]+)", frs_content)

        metadata["feature_branch"] = branch_match.group(1).strip() if branch_match else None
        metadata["created"] = created_match.group(1).strip() if created_match else None
        metadata["status"] = status_match.group(1).strip() if status_match else None
        metadata["input_summary"] = input_match.group(1).strip() if input_match else None

        # Sections list
        sections = re.findall(r"^##\s+(.+)$", frs_content, re.MULTILINE)
        metadata["sections"] = sections

        # Vision
        metadata["vision"] = _extract_section_block("Vision & Problem Statement")

        # Personas
        personas_section = _extract_section_block("Personas")
        personas = []
        for entry in _extract_bullets(personas_section):
            match = re.match(r"\*\*(.+?)\*\*:\s*(.+)", entry)
            if match:
                personas.append({"name": match.group(1).strip(), "description": match.group(2).strip()})
            elif entry:
                personas.append({"name": None, "description": entry})
        metadata["personas"] = personas

        # Scope
        scope_section = _extract_section_block("Scope")
        in_scope = _extract_bullets(_extract_subsection_block(scope_section, "In Scope")) if scope_section else []
        out_scope = _extract_bullets(_extract_subsection_block(scope_section, "Out of Scope")) if scope_section else []
        metadata["scope_in"] = in_scope
        metadata["scope_out"] = out_scope

        # Assumptions & Open Questions
        assumption_section = _extract_section_block("Assumptions & Open Questions")
        assumptions = _extract_bullets(_extract_subsection_block(assumption_section, "Assumptions")) if assumption_section else []
        open_questions = _extract_bullets(_extract_subsection_block(assumption_section, "Open Questions")) if assumption_section else []
        metadata["assumptions"] = assumptions
        metadata["open_questions"] = open_questions

        # User scenarios (summary)
        scenario_pattern = re.compile(
            r"^###\s+(?:Scenario|User Story)\s+\d+\s*-\s*(.*?)\s*\(Priority:\s*(.*?)\)\n(.*?)(?=^###\s+(?:Scenario|User Story)|^##|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        scenarios = []
        for match in scenario_pattern.finditer(frs_content):
            title = match.group(1).strip()
            priority = match.group(2).strip()
            block = match.group(3).strip()
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            summary = next((line for line in lines if not line.startswith("-") and not line.startswith("**")), "")
            bullet_items = [re.sub(r"^[-*]\s*", "", line) for line in lines if line.startswith("-")]
            scenarios.append(
                {
                    "title": title,
                    "priority": priority,
                    "summary": summary,
                    "highlights": bullet_items,
                }
            )
        metadata["user_scenarios"] = scenarios
        metadata["user_scenario_count"] = len(scenarios)

        # Edge cases
        edge_block = re.search(r"###\s+Edge Cases\n(.+?)(?=^##|\Z)", frs_content, re.DOTALL | re.MULTILINE)
        edge_cases = _extract_bullets(edge_block.group(1)) if edge_block else []
        metadata["edge_cases"] = edge_cases

        # Functional overview
        functional_reqs = re.findall(r"\*\*FR-(\d+)\*\*:\s*(.+)", frs_content)
        metadata["functional_requirements"] = [f"FR-{idx}: {desc.strip()}" for idx, desc in functional_reqs]
        metadata["requirements_count"] = len(functional_reqs)

        # Success criteria summary
        success_criteria = re.findall(r"\*\*SC-(\d+)\*\*:\s*(.+)", frs_content)
        metadata["success_criteria"] = [f"SC-{idx}: {desc.strip()}" for idx, desc in success_criteria]

        # Suggested service types (heuristic)
        lower_content = frs_content.lower()
        service_indicators = []
        if "api" in lower_content or "endpoint" in lower_content or "rest" in lower_content:
            service_indicators.append("api")
        if "mobile" in lower_content or "ios" in lower_content or "android" in lower_content:
            service_indicators.append("mobile")
        if "web" in lower_content or "frontend" in lower_content or "ui" in lower_content:
            service_indicators.append("web")
        metadata["suggested_service_types"] = sorted(set(service_indicators))

        # Complexity score heuristic
        complexity_score = (
            metadata["user_scenario_count"]
            + len(functional_reqs)
            + len(edge_cases)
            + len(assumptions)
        )
        metadata["complexity_score"] = complexity_score
        metadata["complexity_level"] = (
            "high" if complexity_score >= 10 else "medium" if complexity_score >= 5 else "low"
        )

        logger.info(
            "FRS 메타데이터 추출 완료 | 시나리오=%d | 요구 요약=%d",
            metadata["user_scenario_count"],
            metadata["requirements_count"],
        )
        return {"success": True, "metadata": metadata}

    except Exception as e:
        logger.exception("FRS 메타데이터 추출 실패")
        return {"success": False, "error": f"Failed to extract FRS metadata: {str(e)}"}
