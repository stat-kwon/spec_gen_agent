from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
import json


def _collect_feedback_lines(
    previous_results: Optional[Dict[str, Any]], document: str
) -> List[str]:
    """이전 피드백에서 특정 문서에 해당하는 항목을 추출합니다."""

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

            target_list = [str(t).strip().lower() for t in target_list if t]
            if document_key in target_list or document in target_list or "general" in target_list:
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

            target_list = [str(t).strip().lower() for t in target_list if t]
            if (
                document_key in target_list
                or document in target_list
                or "general" in target_list
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

            target_list = [str(t).strip().lower() for t in target_list if t]
            if (
                document_key in target_list
                or document in target_list
                or "general" in target_list
            ):
                collected.append(str(note).strip())

    normalized = [line for line in collected if line]
    # preserve order while removing duplicates
    return list(dict.fromkeys(normalized))


def _format_feedback_section(
    previous_results: Optional[Dict[str, Any]],
    document: str,
    closing_sentence: str = "위 피드백을 모두 반영하여 문서를 업데이트하세요.\n",
) -> str:
    lines = _collect_feedback_lines(previous_results, document)
    if not lines:
        return ""

    bullets = "\n".join(f"- {line}" for line in lines)
    return f"\n이전 피드백:\n{bullets}\n\n{closing_sentence}"


def build_requirements_prompt(
    frs_content: str,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """런타임 시점에 요구사항 문서 생성을 위한 사용자 프롬프트를 구성합니다.

    시스템 프롬프트에 정의된 구조/톤 지침은 이 함수에서 수정하지 않습니다.
    """

    metadata_blob = json.dumps(metadata or {}, ensure_ascii=False, indent=2)
    feedback_section = _format_feedback_section(
        previous_results,
        "requirements",
        "위 피드백을 모두 반영하여 요구사항 문서를 업데이트하세요.\n",
    )

    return f"""시스템 프롬프트의 작성 지침을 반드시 따르면서 아래 실행 컨텍스트를 반영해 requirements.md를 작성하세요.

[FRS 전문]
{frs_content}

[서비스 정보]
- 유형: {service_type}

{feedback_section if feedback_section else ""}
[추가 메타데이터]
{metadata_blob}
"""


def build_design_prompt(
    output_dir: str,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
) -> str:
    """설계 문서 생성을 위한 런타임 프롬프트를 구성합니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    feedback_section = _format_feedback_section(
        previous_results,
        "design",
        "위 피드백을 모두 반영하여 설계 문서를 업데이트하세요.\n",
    )
    return (
        "시스템 프롬프트에 정의된 설계 문서 지침을 따르면서 아래 자료를 참고해 "
        "design.md를 작성하세요.\n\n"
        "[필수 입력]\n"
        f'- Requirements 문서: read_spec_file("{requirements_file}") 호출 후 내용을 분석하세요.\n'
        f"- 서비스 유형: {service_type}\n"
        f"{feedback_section}"
    )


def build_tasks_prompt(
    output_dir: str, previous_results: Optional[Dict[str, Any]] = None
) -> str:
    """작업 문서 생성을 위한 런타임 프롬프트를 구성합니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    feedback_section = _format_feedback_section(
        previous_results,
        "tasks",
        "위 피드백을 모두 반영하여 작업 계획 문서를 업데이트하세요.\n",
    )
    return (
        "시스템 프롬프트에 정의된 작업 분해 지침을 따르면서 아래 문서를 참고해 "
        "tasks.md를 작성하세요.\n\n"
        "[필수 입력]\n"
        f'- Requirements 문서: read_spec_file("{requirements_file}")\n'
        f'- Design 문서: read_spec_file("{design_file}")\n'
        f"{feedback_section}"
    )


def build_changes_prompt(
    output_dir: str,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
) -> str:
    """변경 계획 문서 생성을 위한 런타임 프롬프트를 구성합니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    tasks_file = str(Path(output_dir) / "tasks.md")
    feedback_section = _format_feedback_section(
        previous_results,
        "changes",
        "위 피드백을 모두 반영하여 변경 관리 문서를 업데이트하세요.\n",
    )

    return (
        "시스템 프롬프트에 정의된 변경 관리 지침을 따르면서 아래 문서를 참고해 "
        "changes.md를 작성하세요.\n\n"
        "[필수 입력]\n"
        f'- Requirements 문서: read_spec_file("{requirements_file}")\n'
        f'- Design 문서: read_spec_file("{design_file}")\n'
        f'- Tasks 문서: read_spec_file("{tasks_file}")\n'
        f"- 서비스 유형: {service_type}\n"
        f"{feedback_section}"
    )


def build_openapi_prompt(
    output_dir: str, previous_results: Optional[Dict[str, Any]] = None
) -> str:
    """OpenAPI 명세 생성을 위한 런타임 프롬프트를 구성합니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    feedback_section = _format_feedback_section(
        previous_results,
        "openapi",
        "위 피드백을 모두 반영하여 OpenAPI 명세를 업데이트하세요.\n",
    )

    parts = [
        "시스템 프롬프트에 정의된 OpenAPI 3.1 작성 지침을 따르면서 아래 문서를 참고해 "
        "openapi.json을 생성하세요.\n\n",
        "[필수 입력]\n",
        f'- Requirements 문서: read_spec_file("{requirements_file}")\n',
        f'- Design 문서: read_spec_file("{design_file}")\n',
        "\n",
    ]
    if feedback_section:
        parts.append(feedback_section)
    parts.append(
        "출력은 `{`로 시작해 `}`로 끝나는 단 하나의 JSON 객체여야 하며, 추가 텍스트나 코드 "
        "블록을 포함하지 마세요."
    )
    return "".join(parts)


def build_quality_review_prompt(output_dir: str, review_payload: str) -> str:
    """품질 평가 에이전트용 프롬프트를 생성합니다."""

    return (
        "다음은 생성된 명세 문서 목록입니다. 각 문서의 실제 내용은 "
        "read_spec_file(path) 도구를 사용해 필요한 것만 읽으세요.\n"
        f'list_spec_files("{output_dir}")를 호출하면 최신 파일 목록을 확인할 수 있습니다.\n\n'
        f"{review_payload}\n\n"
        "평가 후 반드시 JSON으로만 응답하세요. 필수 키: completeness, consistency, clarity, "
        "technical, overall, feedback (document/note 필드를 가진 배열 — note는 [위치/문제/조치] 형식을 따름), "
        "needs_improvement (불리언)."
    )


def build_consistency_review_prompt(output_dir: str, review_payload: str) -> str:
    """일관성 검증 에이전트용 프롬프트를 생성합니다."""

    return (
        "다음 문서 목록을 바탕으로 교차 검증을 수행하세요. 실제 내용은 필요한 문서만 "
        "read_spec_file(path)로 읽어 일관성을 확인하세요.\n"
        f'list_spec_files("{output_dir}") 호출로 파일 현황을 확인할 수 있습니다.\n'
        "검토 후 JSON으로만 응답하세요.\n\n"
        f"{review_payload}\n\n"
        "필수 JSON 키: issues (document/note 필드를 가진 배열 — note는 [위치/불일치/조치] 형식을 따름), severity (low|medium|high), "
        "cross_references (정수), naming_conflicts (정수)."
    )


def build_coordinator_prompt(
    output_dir: str,
    review_payload: str,
    quality_result: Any,
    consistency_result: Any,
) -> str:
    """코디네이터 에이전트용 프롬프트를 생성합니다."""

    quality_json = (
        json.dumps(quality_result, ensure_ascii=False, indent=2)
        if isinstance(quality_result, dict)
        else str(quality_result)
    )
    consistency_json = (
        json.dumps(consistency_result, ensure_ascii=False, indent=2)
        if isinstance(consistency_result, dict)
        else str(consistency_result)
    )

    return (
        "다음은 생성된 문서 경로와 이전 평가 결과입니다. 필요 시 read_spec_file(path)으로 세부 내용을 확인한 뒤 "
        "최종 승인 여부를 JSON으로 판단하세요.\n"
        f'list_spec_files("{output_dir}") 호출로 최신 문서 목록을 다시 확인할 수 있습니다.\n\n'
        f"문서 목록:\n{review_payload}\n\n"
        f"품질 평가 결과:\n{quality_json}\n\n"
        f"일관성 평가 결과:\n{consistency_json}\n\n"
        "JSON 키: approved (불리언), overall_quality (숫자), decision, required_improvements "
        "(document/note 필드를 가진 오브젝트 배열), message."
    )


def build_improvement_prompt(
    agent_name: str,
    current_content: str,
    feedback_items: Sequence[str],
    required_sections: Sequence[str],
) -> str:
    """문서 개선 프롬프트를 생성합니다."""

    if not feedback_items:
        return ""

    feedback_text = "\n".join(f"- {item}" for item in feedback_items)

    if agent_name == "openapi":
        return (
            "You are updating an existing OpenAPI 3.1 specification based on review feedback.\n"
            "Return ONLY valid JSON for the entire specification. Do not wrap in code fences.\n\n"
            "Current specification:\n"
            f"{current_content}\n\n"
            "Feedback to address:\n"
            f"{feedback_text}"
        )

    section_guidance = ""
    if required_sections:
        bullet_lines = "\n".join(f"- {heading}" for heading in required_sections)
        section_guidance = (
            "모든 필수 섹션 헤더는 아래 목록의 텍스트를 정확히 유지해야 합니다."
            " (한글/영문 병기 포함).\n"
            f"{bullet_lines}\n\n"
        )

    title = f"{agent_name}.md"
    return (
        f"당신은 {title} 문서를 개선하는 기술 문서 작성자입니다.\n"
        "아래 현재 문서를 검토하고 모든 피드백을 반영하여 전체 문서를 재작성하세요.\n"
        "문서 구조와 필수 섹션은 유지하되 내용을 구체화하고 명확하게 다듬으세요.\n"
        "결과는 완성된 한국어 문서 전체를 반환하세요.\n\n"
        f"{section_guidance}"
        "현재 문서:\n"
        "----\n"
        f"{current_content}\n"
        "----\n\n"
        "반영해야 할 피드백:\n"
        f"{feedback_text}"
    )


def pair_required_sections(required_sections: Sequence[str]) -> List[str]:
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
