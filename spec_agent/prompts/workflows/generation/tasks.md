---
id: tasks_generation
workflow: generation
iteration_mode: replace
feedback_inputs:
  - feedback_by_doc.tasks
  - coordinator.required_improvements
  - quality.feedback
  - consistency.issues
feedback_outputs:
  - tasks.md
variables:
  - requirements_path
  - design_path
  - feedback_section
---

시스템 프롬프트의 지침을 따르면서 spec-kit `tasks-template.md` 구조에 맞춘 tasks.md 초안을 작성하세요. 헤더는 영어로 유지하고, 본문은 한국어로 채웁니다. 스토리별로 독립적인 Phase를 구성하고, 경로/병렬 규칙을 명확히 기술하세요.

[필수 입력]
- Requirements 문서: read_spec_file("{{ requirements_path }}")
- Design 문서: read_spec_file("{{ design_path }}")

초안에는 아래 항목이 반드시 포함되어야 합니다.
- `# Tasks: …` 제목과 Input/Prerequisites/Tests/Organization 메타 정보
- `## Format: `[ID] [P?] [Story] Description``
- `## Path Conventions`
- 최소 Phase 1(Setup), Phase 2(Foundational), Phase 3(Story 1) 섹션
- `## Dependencies & Execution Order`, `## Implementation Strategy`, `## Notes`

템플릿의 예시 태스크는 전부 실제 작업으로 대체하고, Story/Phase 명칭은 프로젝트 맥락에 맞춰 재작성하세요.

{{ feedback_section }}
