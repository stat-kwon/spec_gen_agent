---
id: requirements_generation
workflow: generation
iteration_mode: replace
feedback_inputs:
  - feedback_by_doc.requirements
  - coordinator.required_improvements
  - quality.feedback
  - consistency.issues
feedback_outputs:
  - requirements.md
variables:
  - frs_path
  - service_type
  - feedback_section
---

시스템 프롬프트의 작성 지침을 그대로 따르면서 spec-kit의 `spec-template.md`와 동일한 레이아웃을 갖춘 requirements.md 초안을 작성하세요. 헤더 텍스트는 영어 원문을 유지하되, 본문 설명과 표/목록은 모두 한국어로 작성합니다. 첫 번째 버전이라고 해서 단순 요약을 남기지 말고, 아래 요구 구조 전체를 채우고 합리적 가정과 맥락을 명료하게 서술하세요.

[필수 입력]
- FRS 문서: load_frs_document("{{ frs_path }}")
- FRS 메타데이터: extract_frs_metadata(위에서 로드한 content)
- 서비스 유형: {{ service_type }}

반드시 아래 헤더와 순서를 정확히 유지하고, 대괄호/주석으로 표시된 자리에는 실제 내용을 채워 넣으세요. 불확실한 영역은 근거 있는 가정을 포함한 한국어 문장으로 설명하고, 추후 품질 보강 단계가 참고할 수 있도록 가정을 명시하세요.
