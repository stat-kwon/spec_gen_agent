---
id: design_quality_feedback
workflow: quality_feedback
iteration_mode: accumulate
feedback_inputs:
  - coordinator.required_improvements.design
  - quality.feedback.design
  - consistency.issues.design
feedback_outputs:
  - design.md
variables:
  - file_path
  - required_sections_block
  - feedback_payload
---

시스템 프롬프트 지침을 따르면서 spec-kit `plan-template.md` 구조를 유지한 채 design.md(Implementation Plan)를 전면 재작성하세요. 헤더는 영어 원문을 유지하고, 본문은 모두 한국어로 작성합니다. 피드백이 요구한 보강 지점을 분석해 Summary~Complexity Tracking까지 모든 섹션의 정합성을 다시 맞추세요.

필수 준비:
- read_spec_file("{{ file_path }}")로 현재 문서를 검토하고 부족한 점을 요약하세요.
- 피드백이 언급하지 않은 연관 섹션까지 영향을 검토해 필요한 경우 함께 보강하세요.

반드시 다음 헤더를 정확히 포함하고 순서를 유지하세요:
{{ required_sections_block }}

샘플 문구나 placeholder는 모두 제거하고, 재작성된 문서 한 본만 출력합니다. 필요 시 구조를 재정렬해도 되지만, 필수 헤더는 삭제하면 안 됩니다.

아래 개선 지시(JSON 배열)를 모두 반영해 최종 문서만 반환하세요.
개선 지시 목록(JSON):
{{ feedback_payload }}
