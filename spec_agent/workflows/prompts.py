from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
import json


def build_requirements_prompt(
    frs_content: str,
    service_type: str,
    previous_results: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """요구사항 문서 생성을 위한 프롬프트를 만듭니다."""

    feedback_section = ""
    if previous_results and "coordinator" in previous_results:
        try:
            coordinator_data = json.loads(
                previous_results["coordinator"].get("content", "{}")
            )
            improvements = coordinator_data.get("required_improvements", [])
            if improvements:
                feedback_lines = "\n".join(f"- {item}" for item in improvements)
                feedback_section = (
                    f"\n이전 피드백:\n{feedback_lines}\n\n"
                    "위 피드백을 반영하여 개선된 요구사항을 작성하세요.\n"
                )
        except Exception:
            pass

    metadata_blob = json.dumps(metadata or {}, ensure_ascii=False, indent=2)

    return f"""다음 FRS 내용을 기반으로 requirements.md를 생성하세요:

FRS:
{frs_content}

서비스 유형: {service_type}

{feedback_section}

요구사항:
1. 기능 요구사항
2. 비기능 요구사항
3. 엣지 케이스
4. 리스크 및 완화 방안
5. 서비스 메트릭
6. 한국어로 작성

추가 메타데이터:
{metadata_blob}"""


def build_design_prompt(output_dir: str, service_type: str) -> str:
    """설계 문서 생성을 위한 프롬프트를 만듭니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    return f"""다음 요구사항 파일을 읽어서 상세한 design.md를 생성하세요:

요구사항 파일을 확인하려면 read_spec_file("{requirements_file}")를 호출하세요.
서비스 유형: {service_type}

요구사항:
1. 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함 (```mermaid 블록)
3. 데이터 모델 정의
4. API 계약 설계
5. 보안 및 성능 고려사항
6. 한국어로 작성

지침: read_spec_file("{requirements_file}")로 불러온 내용을 바탕으로 설계 문서를 작성하세요."""


def build_tasks_prompt(output_dir: str) -> str:
    """작업 문서 생성을 위한 프롬프트를 만듭니다."""

    design_file = str(Path(output_dir) / "design.md")
    return f"""다음 설계 파일을 읽어서 상세한 tasks.md를 생성하세요:

설계 파일을 확인하려면 read_spec_file("{design_file}")를 호출하세요.

요구사항:
1. Epic/Story/Task 계층 구조
2. 각 작업에 대한 명확한 설명
3. 예상 시간 및 우선순위
4. DoD (Definition of Done) 체크리스트
5. 의존성 표시
6. 한국어로 작성

지침: read_spec_file("{design_file}")로 불러온 내용을 바탕으로 작업 분해 문서를 작성하세요."""


def build_changes_prompt(output_dir: str, service_type: str) -> str:
    """변경 계획 문서 생성을 위한 프롬프트를 만듭니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")
    tasks_file = str(Path(output_dir) / "tasks.md")

    return f"""프로젝트 배포를 위한 상세한 changes.md를 생성하세요:

요구사항 파일 경로: {requirements_file}
설계 파일 경로: {design_file}

서비스 유형: {service_type}

참고 문서:
- Requirements: read_spec_file("{requirements_file}")
- Design: read_spec_file("{design_file}")
- Tasks: read_spec_file("{tasks_file}")

반드시 아래 5개의 섹션 헤더를 **동일한 텍스트**(슬래시(`/`)와 `&` 주변에 공백 없이)로 포함하세요. 영어 혹은 한글만 출력하면 검증에 실패합니다.
- ## 버전 이력/Version History
- ## 변경 요약/Change Summary
- ## 영향/위험/Impact/Risk
- ## 롤백 계획/Rollback Plan
- ## 알려진 문제/Known Issues

샘플 구조:
```
## 버전 이력/Version History
| 버전/Version | 릴리스 날짜/Release Date | 변경 사항/Change Description |
|--------------|--------------------------|------------------------------|

## 변경 요약/Change Summary
- 항목...

## 영향/위험/Impact/Risk
- 항목...

## 롤백 계획/Rollback Plan
- 항목...

## 알려진 문제/Known Issues
- 항목...
```

각 섹션에 구체적이고 실행 가능한 내용을 채우고, 문서 작성 후 apply_template("<your_content>", "changes")가 success=True를 반환하는지 반드시 확인하세요."""


def build_openapi_prompt(output_dir: str) -> str:
    """OpenAPI 생성을 위한 프롬프트를 만듭니다."""

    requirements_file = str(Path(output_dir) / "requirements.md")
    design_file = str(Path(output_dir) / "design.md")

    return f"""Create a complete OpenAPI 3.1 specification in JSON format.

Use read_spec_file("{requirements_file}") and read_spec_file("{design_file}") to load the source material before writing the specification.

IMPORTANT:
1. Read the contents of both files first
2. Respond with only valid JSON. Start with {{ and end with }}
3. Include:
   - OpenAPI 3.1.0 specification
   - Complete info section with title, version, description
   - All authentication schemes (Bearer JWT)
   - 5-10 core endpoints based on requirements
   - Detailed request/response schemas
   - Error responses (400, 401, 404, 500)
   - Components section with reusable schemas

Output pure JSON only - no text before or after."""


def build_quality_review_prompt(output_dir: str, review_payload: str) -> str:
    """품질 평가 에이전트용 프롬프트를 생성합니다."""

    return (
        "다음은 생성된 명세 문서 목록입니다. 각 문서의 실제 내용은 "
        "read_spec_file(path) 도구를 사용해 필요한 것만 읽으세요.\n"
        f'list_spec_files("{output_dir}")를 호출하면 최신 파일 목록을 확인할 수 있습니다.\n\n'
        f"{review_payload}\n\n"
        "평가 후 반드시 JSON으로만 응답하세요. 필수 키: completeness, consistency, clarity, "
        "technical, overall, feedback (document/note 필드를 가진 오브젝트 배열), needs_improvement (불리언)."
    )


def build_consistency_review_prompt(output_dir: str, review_payload: str) -> str:
    """일관성 검증 에이전트용 프롬프트를 생성합니다."""

    return (
        "다음 문서 목록을 바탕으로 교차 검증을 수행하세요. 실제 내용은 필요한 문서만 "
        "read_spec_file(path)로 읽어 일관성을 확인하세요.\n"
        f'list_spec_files("{output_dir}") 호출로 파일 현황을 확인할 수 있습니다.\n'
        "검토 후 JSON으로만 응답하세요.\n\n"
        f"{review_payload}\n\n"
        "필수 JSON 키: issues (document/note 필드를 가진 오브젝트 배열), severity (low|medium|high), "
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


def build_generation_prompt_from_previous(
    agent_name: str, previous_contents: Dict[str, str], service_type: str
) -> str:
    """이전 출력에 기반해 문서를 생성하는 프롬프트를 만듭니다."""

    if agent_name == "design":
        requirements = previous_contents.get("requirements", "")[:3000]
        return f"""다음 요구사항을 바탕으로 상세한 design.md를 생성하세요:

요구사항:
{requirements}

서비스 유형: {service_type}

요구사항:
1. 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함 (```mermaid 블록)
3. 데이터 모델 정의
4. API 계약 설계
5. 보안 및 성능 고려사항
6. 한국어로 작성"""

    if agent_name == "tasks":
        design = previous_contents.get("design", "")[:3000]
        return f"""다음 설계를 바탕으로 상세한 tasks.md를 생성하세요:

설계:
{design}

요구사항:
1. Epic/Story/Task 계층 구조
2. 각 작업에 대한 명확한 설명
3. 예상 시간 및 우선순위
4. DoD (Definition of Done) 체크리스트
5. 의존성 표시
6. 한국어로 작성"""

    if agent_name == "changes":
        return f"""프로젝트 배포를 위한 상세한 changes.md를 생성하세요:

서비스 유형: {service_type}

요구사항:
1. 버전 이력
2. 변경 사항 요약
3. 영향도 및 위험 분석
4. 롤백 계획
5. 알려진 이슈
6. 한국어로 작성"""

    if agent_name == "openapi":
        requirements = previous_contents.get("requirements", "")[:2000]
        design = previous_contents.get("design", "")[:2000]
        return f"""OpenAPI 3.1 명세를 JSON 형식으로 생성하세요:

요구사항:
{requirements}

설계:
{design}

요구사항:
1. 유효한 JSON 형식 (마크다운 블록 없이)
2. OpenAPI 3.1 스펙 준수
3. 5-10개의 핵심 엔드포인트
4. 요청/응답 스키마 포함
5. 인증 및 오류 처리
6. JSON만 출력 (설명 없음)"""

    return "작업을 수행하세요."


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
