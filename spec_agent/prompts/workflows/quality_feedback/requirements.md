---
id: requirements_quality_feedback
workflow: quality_feedback
iteration_mode: accumulate
feedback_inputs:
  - coordinator.required_improvements.requirements
  - quality.feedback.requirements
  - consistency.issues.requirements
feedback_outputs:
  - requirements.md
variables:
  - file_path
  - required_sections_block
  - feedback_payload
---

시스템 프롬프트 지침을 따르면서 spec-kit `spec-template.md` 구조를 **완전히** 충족하도록 requirements.md를 재작성하세요. 헤더는 영어 원문을 유지하고, 본문은 모두 한국어로 갱신해야 합니다. 아래 피드백을 분석해 누락된 사용자 시나리오, 요구사항, 성공 지표를 보강하고 문서 일관성을 회복하세요.

필수 준비:
- read_spec_file("{{ file_path }}")로 최신 requirements.md 내용을 확인하고 문제점을 요약하세요.
- 피드백에서 언급된 항목 외에도 영향을 받는 섹션이 있는지 교차 검증하세요.

반드시 다음 헤더를 정확히 포함하고 순서를 유지하세요:
{{ required_sections_block }}

문서는 부분 수정이 아니라 **완성도 있는 최신 버전**이어야 합니다. 샘플 문구나 placeholder, 이전 버전의 남은 문장을 모두 제거하고, 개선 사항을 명확히 드러내세요.

아래 개선 지시(JSON 배열)를 모두 반영해 최종 문서만 반환하세요.
개선 지시 목록(JSON):
{{ feedback_payload }}

출력은 재작성된 requirements.md 전체 한 본으로 제한하며, 변경 요약이나 추가 설명을 덧붙이지 마세요.
