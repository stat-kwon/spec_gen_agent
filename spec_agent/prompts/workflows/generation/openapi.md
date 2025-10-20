---
id: openapi_generation
workflow: generation
iteration_mode: replace
feedback_inputs:
  - feedback_by_doc.openapi
  - coordinator.required_improvements
  - quality.feedback
  - consistency.issues
feedback_outputs:
  - openapi.json
variables:
  - requirements_path
  - design_path
  - feedback_section
---

시스템 프롬프트에 정의된 OpenAPI 3.1 작성 지침을 따르면서 아래 문서를 참고해 openapi.json을 생성하세요.

[필수 입력]
- Requirements 문서: read_spec_file("{{ requirements_path }}")
- Design 문서: read_spec_file("{{ design_path }}")

{{ feedback_section }}

출력은 `{`로 시작해 `}`로 끝나는 단 하나의 JSON 객체여야 하며, 추가 텍스트나 코드 블록을 포함하지 마세요.
