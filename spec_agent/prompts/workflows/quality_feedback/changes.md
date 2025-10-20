---
id: changes_quality_feedback
workflow: quality_feedback
iteration_mode: accumulate
feedback_inputs:
  - coordinator.required_improvements.changes
  - quality.feedback.changes
  - consistency.issues.changes
feedback_outputs:
  - changes.md
variables:
  - file_path
  - required_sections_block
  - feedback_payload
---

배포/변경 관리 문서를 최신 상태로 재작성하세요. 헤더 구조는 제공된 순서를 유지하고, 본문은 한국어로 작성합니다. 영향 분석, 위험 완화, 롤백 전략 등 피드백이 요구한 보강 사항을 명확히 반영하세요.

필수 준비:
- read_spec_file("{{ file_path }}")로 기존 문서를 검토하고 반영 여부를 표로 정리하세요.
- 새 변경 사항이 추가되면 버전 이력과 영향 범위를 함께 업데이트하세요.

필수 헤더:
{{ required_sections_block }}

아래 개선 지시(JSON 배열)를 모두 반영해 최종 문서만 반환하세요.
개선 지시 목록(JSON):
{{ feedback_payload }}
