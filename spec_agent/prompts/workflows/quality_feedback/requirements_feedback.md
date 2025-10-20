---
id: requirements_quality_feedback_summary
workflow: quality_feedback
iteration_mode: accumulate
feedback_inputs:
  - feedback_by_doc.requirements
  - coordinator.required_improvements.requirements
  - quality.feedback.requirements
  - consistency.issues.requirements
feedback_outputs:
  - requirements.feedback_section
variables:
  - feedback_bullets
  - closing_sentence
---

아래 항목은 문서 품질을 높이기 위해 반드시 반영해야 할 보강 지점입니다.

{{ feedback_bullets }}

{{ closing_sentence }}
