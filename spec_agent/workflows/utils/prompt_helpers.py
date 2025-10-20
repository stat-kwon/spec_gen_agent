"""보조 프롬프트 유틸리티."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from spec_agent.prompts import render_prompt


def collect_feedback_lines(
    previous_results: Optional[Dict[str, Any]],
    document: str,
) -> List[str]:
    """이전 품질 평가 결과에서 특정 문서의 피드백을 수집합니다."""

    if not isinstance(previous_results, dict):
        return []

    document_key = document.lower()
    collected: List[str] = []

    feedback_map = previous_results.get("feedback_by_doc")
    if isinstance(feedback_map, dict):
        raw_lines = feedback_map.get(document_key) or feedback_map.get(document)
        if isinstance(raw_lines, str):
            cleaned = raw_lines.strip()
            if cleaned:
                collected.append(cleaned)
        elif isinstance(raw_lines, Iterable):
            collected.extend(str(line).strip() for line in raw_lines if line)

    coordinator_result = previous_results.get("coordinator")
    if isinstance(coordinator_result, dict):
        for item in coordinator_result.get("required_improvements", []) or []:
            if isinstance(item, dict):
                targets = item.get("documents") or item.get("document")
                notes = item.get("note") or item.get("message") or item.get("detail")
            else:
                targets = None
                notes = item

            if not notes:
                continue

            target_list = targets
            if target_list is None:
                target_list = []
            if not isinstance(target_list, (list, tuple, set)):
                target_list = [target_list]

            normalized_targets = [str(t).strip().lower() for t in target_list if t]
            if (
                document_key in normalized_targets
                or document in normalized_targets
                or "general" in normalized_targets
            ):
                collected.append(str(notes).strip())

    quality_result = previous_results.get("quality")
    if isinstance(quality_result, dict):
        for item in quality_result.get("feedback", []) or []:
            if isinstance(item, dict):
                targets = item.get("documents") or item.get("document")
                note = item.get("note") or item.get("message") or item.get("detail")
            else:
                targets = None
                note = item

            if not note:
                continue

            target_list = targets
            if target_list is None:
                target_list = []
            if not isinstance(target_list, (list, tuple, set)):
                target_list = [target_list]

            normalized_targets = [str(t).strip().lower() for t in target_list if t]
            if (
                document_key in normalized_targets
                or document in normalized_targets
                or "general" in normalized_targets
            ):
                collected.append(str(note).strip())

    consistency_result = previous_results.get("consistency")
    if isinstance(consistency_result, dict):
        for item in consistency_result.get("issues", []) or []:
            if isinstance(item, dict):
                targets = item.get("documents") or item.get("document")
                note = item.get("note") or item.get("message") or item.get("detail")
            else:
                targets = None
                note = item

            if not note:
                continue

            target_list = targets
            if target_list is None:
                target_list = []
            if not isinstance(target_list, (list, tuple, set)):
                target_list = [target_list]

            normalized_targets = [str(t).strip().lower() for t in target_list if t]
            if (
                document_key in normalized_targets
                or document in normalized_targets
                or "general" in normalized_targets
            ):
                collected.append(str(note).strip())

    normalized = [line for line in collected if line]
    return list(dict.fromkeys(normalized))


def format_feedback_section(
    previous_results: Optional[Dict[str, Any]],
    document: str,
    closing_sentence: str,
) -> str:
    """프롬프트에 삽입할 피드백 섹션을 생성합니다."""

    lines = collect_feedback_lines(previous_results, document)
    if not lines:
        return ""

    bullets = "\n".join(f"- {line}" for line in lines)

    template_map = {
        "requirements": "workflows/quality_feedback/requirements_feedback.md",
    }

    template_path = template_map.get(document.lower())
    if template_path:
        context = {
            "feedback_bullets": bullets,
            "closing_sentence": closing_sentence,
        }
        rendered = render_prompt(template_path, context)
        return rendered + "\n"

    return f"\n이전 피드백:\n{bullets}\n\n{closing_sentence}\n"


def pair_required_sections(required_sections: List[str]) -> List[str]:
    """템플릿 필수 섹션 목록을 개선 프롬프트용으로 정리합니다."""

    section_pairs: List[str] = []
    for idx in range(0, len(required_sections), 2):
        first = required_sections[idx]
        second = (
            required_sections[idx + 1] if idx + 1 < len(required_sections) else first
        )
        if second and second != first:
            section_pairs.append(f"{first}/{second}")
        else:
            section_pairs.append(first)
    return section_pairs
