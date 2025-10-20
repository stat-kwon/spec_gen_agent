---
id: openapi_quality_feedback
workflow: quality_feedback
iteration_mode: accumulate
feedback_inputs:
  - coordinator.required_improvements.openapi
  - quality.feedback.openapi
  - consistency.issues.openapi
feedback_outputs:
  - openapi.json
variables:
  - file_path
  - feedback_payload
---

기존 OpenAPI 3.1 명세를 피드백에 맞춰 전면 수정하세요. JSON만 반환해야 하며, 스키마 누락·예제 불일치·보안 스펙 등을 모두 보강합니다.

필수 준비:
- read_spec_file("{{ file_path }}")로 최신 명세를 확인하고, 피드백과 차이점을 정리하세요.
- 엔드포인트, 스키마, 보안 스키마, 예제 응답에 대한 정합성을 다시 검증하세요.

개선 지시(JSON):
{{ feedback_payload }}

출력은 `{`로 시작해 `}`로 끝나는 단일 JSON 객체여야 하며, 추가 텍스트나 주석을 포함하지 마세요.
