from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from spec_agent.prompts import render_prompt
from .utils.prompt_helpers import format_feedback_section


def build_requirements_prompt(
    frs_path: Path,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
) -> str:
    """Runtime prompt for generating requirements.md."""

    feedback_section = format_feedback_section(
        previous_results,
        "requirements",
        "위 피드백을 모두 반영하여 요구사항 문서를 업데이트하세요.",
    )

    context = {
        "frs_path": str(frs_path),
        "service_type": service_type,
        "feedback_section": feedback_section.strip(),
    }

    return render_prompt("workflows/generation/requirements.md", context)


def build_design_prompt(
    output_dir: str,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
) -> str:
    requirements_file = str(Path(output_dir) / "requirements.md")
    feedback_section = format_feedback_section(
        previous_results,
        "design",
        "위 피드백을 모두 반영하여 설계 문서를 업데이트하세요.",
    )

    context = {
        "requirements_path": requirements_file,
        "service_type": service_type,
        "feedback_section": feedback_section.strip(),
    }
    return render_prompt("workflows/generation/design.md", context)


def build_tasks_prompt(
    output_dir: str, previous_results: Optional[Dict[str, Any]] = None
) -> str:
    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    feedback_section = format_feedback_section(
        previous_results,
        "tasks",
        "위 피드백을 모두 반영하여 작업 계획 문서를 업데이트하세요.",
    )

    context = {
        "requirements_path": requirements_file,
        "design_path": design_file,
        "feedback_section": feedback_section.strip(),
    }
    return render_prompt("workflows/generation/tasks.md", context)


def build_changes_prompt(
    output_dir: str,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
) -> str:
    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    tasks_file = str(Path(output_dir) / "tasks.md")
    feedback_section = format_feedback_section(
        previous_results,
        "changes",
        "위 피드백을 모두 반영하여 변경 관리 문서를 업데이트하세요.",
    )

    context = {
        "requirements_path": requirements_file,
        "design_path": design_file,
        "tasks_path": tasks_file,
        "service_type": service_type,
        "feedback_section": feedback_section.strip(),
    }
    return render_prompt("workflows/generation/changes.md", context)


def build_openapi_prompt(
    output_dir: str, previous_results: Optional[Dict[str, Any]] = None
) -> str:
    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    feedback_section = format_feedback_section(
        previous_results,
        "openapi",
        "위 피드백을 모두 반영하여 OpenAPI 명세를 업데이트하세요.",
    )

    context = {
        "requirements_path": requirements_file,
        "design_path": design_file,
        "feedback_section": feedback_section.strip(),
    }
    return render_prompt("workflows/generation/openapi.md", context)


def build_quality_review_prompt(output_dir: str, review_payload: str) -> str:
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
    applied_feedback: Optional[Dict[str, Sequence[str]]] = None,
) -> str:
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

    applied_section = ""
    if applied_feedback:
        applied_section = (
            "\n이미 반영된 개선 항목 목록(JSON):\n"
            f"{json.dumps(applied_feedback, ensure_ascii=False, indent=2)}\n\n"
            "위 목록에 포함된 항목은 다시 요구하지 마세요.\n"
        )

    return (
        "다음은 생성된 문서 경로와 이전 평가 결과입니다. 필요 시 read_spec_file(path)으로 세부 내용을 확인한 뒤 "
        "최종 승인 여부를 JSON으로 판단하세요.\n"
        f'list_spec_files("{output_dir}") 호출로 최신 문서 목록을 다시 확인할 수 있습니다.\n\n'
        f"문서 목록:\n{review_payload}\n\n"
        f"품질 평가 결과:\n{quality_json}\n\n"
        f"일관성 평가 결과:\n{consistency_json}\n\n"
        f"{applied_section}"
        "JSON 키: approved (불리언), overall_quality (숫자), decision, required_improvements "
        "(document/note 필드를 가진 오브젝트 배열), message. 이미 해결된 항목이나 동일한 요청을 반복하지 말고 "
        "새롭게 필요한 개선만 제시하세요."
    )


def build_improvement_prompt(
    agent_name: str,
    current_content: str,
    feedback_items: Sequence[str],
    required_sections: Sequence[str],
    file_path: str,
) -> str:
    if not feedback_items:
        return ""

    feedback_payload = json.dumps(
        [{"document": agent_name, "note": item} for item in feedback_items],
        ensure_ascii=False,
        indent=2,
    )

    template_map = {
        "requirements": "workflows/quality_feedback/requirements.md",
        "design": "workflows/quality_feedback/design.md",
        "tasks": "workflows/quality_feedback/tasks.md",
        "changes": "workflows/quality_feedback/changes.md",
    }

    if agent_name == "openapi":
        context = {
            "file_path": file_path,
            "feedback_payload": feedback_payload,
        }
        return render_prompt("workflows/quality_feedback/openapi.md", context)

    section_guidance = ""
    if required_sections:
        bullets = "\n".join(f"- {heading}" for heading in required_sections)
        section_guidance = (
            "필수 섹션 헤더는 아래 목록을 정확히 유지해야 합니다 (한글/영문 병기 포함).\n"
            f"{bullets}\n"
        )

    template_path = template_map.get(agent_name)
    if template_path:
        context = {
            "file_path": file_path,
            "required_sections_block": section_guidance,
            "feedback_payload": feedback_payload,
        }
        return render_prompt(template_path, context)

    # 기타 문서 유형에 대한 기본 처리
    lines = [
        "시스템 프롬프트 지침을 그대로 따라 문서를 전체 재작성하세요.",
        f'필수: read_spec_file("{file_path}")를 호출해 최신 본문을 확인한 뒤 작업합니다.',
        "아래 개선 지시는 모두 문서 본문에 반영해야 하며, 이미 반영된 내용은 더 명확하게 정리하세요.",
        f"산출물은 완성된 {agent_name}.md 전체입니다. 요약이나 부가 설명은 포함하지 마세요.",
    ]
    if section_guidance:
        lines.append(section_guidance)
    lines.extend(
        [
            "개선 지시 목록(JSON):",
            feedback_payload,
            "",
            "모든 항목이 반영되었는지 확인한 뒤 최종 문서만 반환하세요.",
        ]
    )
    return "\n".join(lines) + "\n"
