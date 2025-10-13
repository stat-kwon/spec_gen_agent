"""템플릿 처리 및 검증 도구들."""

import re
from typing import Dict, Any, List
from strands import tool


@tool
def apply_template(content: str, template_type: str) -> Dict[str, Any]:
    """
    템플릿 구조 검증 및 포맷팅을 적용합니다.

    Args:
        content: 검증할 생성된 컨텐츠
        template_type: 템플릿 타입 (requirements, design, tasks, changes, openapi)

    Returns:
        검증 결과와 포맷된 컨텐츠를 담은 딕셔너리
    """
    try:
        template_structures = {
            "requirements": [
                # 한글/영어 모두 지원
                "헤더/메타", "Header/Meta",
                "범위", "Scope", 
                "기능 요구사항", "Functional Requirements",
                "오류 요구사항", "Error Requirements",
                "보안 & 개인정보", "Security & Privacy",
                "관측 가능성", "Observability",
                "수용 기준", "Acceptance Criteria",
            ],
            "design": [
                # 한글/영어 모두 지원
                "아키텍처", "Architecture",
                "시퀀스 다이어그램", "Sequence Diagram",
                "데이터 모델", "Data Model", 
                "API 계약", "API Contract",
                "보안 & 권한", "Security & Permissions",
                "성능 목표", "Performance Goals",
            ],
            "tasks": [
                # 한글/영어 모두 지원
                "에픽", "Epic", 
                "스토리", "Story", 
                "태스크", "Task", 
                "DoD"  # DoD는 공통
            ],
            "changes": [
                # 한글/영어 모두 지원
                "버전 이력", "Version History",
                "변경 요약", "Change Summary", 
                "영향/위험", "Impact/Risk",
                "롤백 계획", "Rollback Plan",
                "알려진 문제", "Known Issues",
            ],
        }

        if template_type not in template_structures:
            return {
                "success": False,
                "error": f"Unknown template type: {template_type}",
            }

        required_sections = template_structures[template_type]
        missing_sections = []

        # Check for required sections (한글/영어 쌍으로 체크)
        # 한글/영어가 쌍으로 있으므로 2개씩 묶어서 처리
        section_pairs = []
        for i in range(0, len(required_sections), 2):
            if i + 1 < len(required_sections):
                section_pairs.append((required_sections[i], required_sections[i + 1]))
            else:
                section_pairs.append((required_sections[i], required_sections[i]))  # 단일 섹션인 경우
        
        for korean_section, english_section in section_pairs:
            # 한글 또는 영어 중 하나라도 찾으면 OK
            korean_found = re.search(r"#{1,3}\s+.*" + re.escape(korean_section), content, re.IGNORECASE)
            english_found = re.search(r"#{1,3}\s+.*" + re.escape(english_section), content, re.IGNORECASE)
            
            if not korean_found and not english_found:
                missing_sections.append(f"{korean_section}/{english_section}")

        # Extract existing sections
        found_sections = re.findall(r"^#{1,3}\s+(.+)$", content, re.MULTILINE)

        return {
            "success": len(missing_sections) == 0,
            "content": content,
            "template_type": template_type,
            "required_sections": required_sections,
            "found_sections": found_sections,
            "missing_sections": missing_sections,
            "compliance_score": (len(section_pairs) - len(missing_sections))
            / len(section_pairs),
        }

    except Exception as e:
        return {"success": False, "error": f"Template application failed: {str(e)}"}


@tool
def validate_markdown_structure(content: str) -> Dict[str, Any]:
    """
    마크다운 구조와 포맷팅을 검증합니다.

    Args:
        content: 검증할 마크다운 컨텐츠

    Returns:
        검증 결과를 담은 딕셔너리
    """
    try:
        issues = []
        warnings = []

        # Check for proper heading hierarchy
        headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        if headings:
            prev_level = 0
            for heading_marks, heading_text in headings:
                current_level = len(heading_marks)
                if current_level > prev_level + 1:
                    issues.append(
                        f"Heading level jump: '{heading_text}' (level {current_level})"
                    )
                prev_level = current_level

        # Check for empty sections
        sections = re.split(r"^#{1,6}\s+.+$", content, flags=re.MULTILINE)[1:]
        for i, section in enumerate(sections):
            if not section.strip():
                warnings.append(f"Empty section found at position {i+1}")

        # Check for proper list formatting
        list_items = re.findall(r"^[\s]*[-*+]\s*(.*)$", content, re.MULTILINE)
        for item in list_items:
            if not item.strip():
                issues.append("Empty list item found")

        # Check for code blocks
        code_blocks = re.findall(r"```(\w*)\n(.*?)\n```", content, re.DOTALL)
        for lang, code in code_blocks:
            if not code.strip():
                warnings.append(f"Empty code block found (language: {lang or 'none'})")

        return {
            "success": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "heading_count": len(headings),
            "list_item_count": len(list_items),
            "code_block_count": len(code_blocks),
        }

    except Exception as e:
        return {"success": False, "error": f"Markdown validation failed: {str(e)}"}
