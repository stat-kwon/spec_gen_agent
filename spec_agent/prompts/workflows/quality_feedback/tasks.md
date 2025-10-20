---
id: tasks_quality_feedback
workflow: quality_feedback
iteration_mode: accumulate
feedback_inputs:
  - coordinator.required_improvements.tasks
  - quality.feedback.tasks
  - consistency.issues.tasks
feedback_outputs:
  - tasks.md
variables:
  - file_path
  - required_sections_block
  - feedback_payload
---

시스템 프롬프트 지침을 따르면서 spec-kit `tasks-template.md` 구조를 유지해 tasks.md를 전면 재작성하세요. 헤더는 영어 원문을 유지하고, 본문은 모두 한국어로 작성합니다. 피드백이 요구한 작업 분해·우선순위·병렬 가능성·테스트 범위를 명확히 반영하세요.

필수 준비:
- read_spec_file("{{ file_path }}")로 기존 작업 계획을 검토하고, 흐름 상 충돌이나 빈틈을 정리하세요.
- 스토리-태스크-테스트 간 추적성을 다시 검증해 필요 시 구조를 재구성하세요.

필수 헤더:
{{ required_sections_block }}

아래 개선 지시(JSON 배열)를 모두 반영해 최종 문서만 반환하세요.
개선 지시 목록(JSON):
{{ feedback_payload }}
