---
id: design_generation
workflow: generation
iteration_mode: replace
feedback_inputs:
  - feedback_by_doc.design
  - coordinator.required_improvements
  - quality.feedback
  - consistency.issues
feedback_outputs:
  - design.md
variables:
  - requirements_path
  - service_type
  - feedback_section
---

시스템 프롬프트의 지침을 따르면서 spec-kit `plan-template.md` 형식의 design.md(Implementation Plan)를 초안으로 작성하세요. 헤더는 영어로 유지하고, 본문은 한국어로 채웁니다. 초안이라도 모든 필수 섹션을 빠짐없이 채우고, 합리적 가정을 명시하세요.

[필수 입력]
- Requirements 문서: read_spec_file("{{ requirements_path }}")로 요구사항을 정리하세요.
- 서비스 유형: {{ service_type }}

반드시 다음 항목을 포함하세요.
- `# Implementation Plan: …` 제목과 Branch/Date/Spec 메타데이터
- `## Summary`, `## Technical Context`, `## Constitution Check`, `## Project Structure`(하위 섹션 포함), `## Complexity Tracking`

템플릿의 주석이나 예시는 모두 실 데이터로 대체하고, 미정 항목은 “근거 있는 가정”을 명시하세요.

{{ feedback_section }}
