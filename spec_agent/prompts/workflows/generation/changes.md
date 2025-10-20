---
id: changes_generation
workflow: generation
iteration_mode: replace
feedback_inputs:
  - feedback_by_doc.changes
  - coordinator.required_improvements
  - quality.feedback
  - consistency.issues
feedback_outputs:
  - changes.md
variables:
  - requirements_path
  - design_path
  - tasks_path
  - service_type
  - feedback_section
---

시스템 프롬프트에 정의된 변경 관리 지침을 따르면서 아래 문서를 참고해 changes.md를 작성하세요.

[필수 입력]
- Requirements 문서: read_spec_file("{{ requirements_path }}")
- Design 문서: read_spec_file("{{ design_path }}")
- Tasks 문서: read_spec_file("{{ tasks_path }}")
- 서비스 유형: {{ service_type }}

{{ feedback_section }}
