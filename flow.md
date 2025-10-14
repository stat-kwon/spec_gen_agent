# 명세 생성 워크플로우 흐름

```mermaid
flowchart TD
    subgraph Sequential Pipeline
        A[FRS 경로 입력] --> B[프로젝트 컨텍스트 초기화<br/>- FRS 로드<br/>- 출력 디렉터리 준비]
        B --> C[Git 브랜치 생성 (옵션)]
        C --> D[에이전트 초기화]
        D --> E[[SequentialDocumentGenerator]]
        E --> R[requirements 에이전트<br/>requirements.md 생성]
        R --> G[design 에이전트<br/>design.md 생성]
        G --> T[tasks 에이전트<br/>tasks.md 생성]
        T --> CH[changes 에이전트<br/>changes.md 생성]
        CH --> O{서비스 유형이 API인가?}
        O -- 예 --> OA[openapi 에이전트<br/>openapi.json 생성]
        O -- 아니오 --> V[템플릿 검증 & 파일 저장]
        OA --> V
        V --> S[저장 파일 집계 & Git 커밋 (옵션)]
    end

    subgraph Adaptive Quality Loop
        S --> Q[[QualityImprovementManager]]
        Q --> QA[Quality Assessor<br/>품질 평가 JSON]
        Q --> QC[Consistency Checker<br/>일관성 이슈 JSON]
        QA --> CO[Coordinator<br/>승인/개선 지시]
        QC --> CO
        CO --> D1{승인 여부?}
        D1 -- 네 --> R1[최종 결과 반환]
        D1 -- 아니오 --> F[피드백 통합]
        F --> U[문서별 개선 프롬프트 작성]
        U --> RA[해당 생성 에이전트 재호출<br/>requirements/design/tasks/changes/openapi]
        RA --> V
    end
```

- **Sequential Pipeline**: `SequentialDocumentGenerator`가 고정 순서로 각 에이전트를 호출하고, `apply_template`·`validate_openapi_spec`을 통해 출력 품질을 강제합니다. 이 구간은 Agentic 요소가 거의 없으며, 순차 파이프라인으로 보면 됩니다.
- **Adaptive Quality Loop**: `QualityImprovementManager`만이 평가 결과에 따라 루프 횟수·대상 문서·프롬프트를 자율적으로 조정하는 영역입니다. 승인 시 루프가 종료되고, 그렇지 않으면 필요한 문서만 재생성하도록 피드백을 전달합니다.

## 3. 에이전트별 역할 요약

| 에이전트 | 주요 입력 | 출력 문서 | 특징 |
| --- | --- | --- | --- |
| `requirements` | FRS 전문, 이전 피드백 | `requirements.md` | 요구사항 ID, 기능/비기능 구분 |
| `design` | `requirements.md` | `design.md` | 시퀀스 다이어그램, 데이터 모델 포함 |
| `tasks` | `design.md` | `tasks.md` | Epic/Story/Task 계층 구조 |
| `changes` | requirements/design/tasks | `changes.md` | 다국어 섹션 헤더 검증 필수 |
| `openapi` (API 한정) | requirements/design | `openapi.json` | OpenAPI 3.1 JSON, 인증/에러 스키마 |
| `quality_assessor` | 생성 문서 목록 | JSON 평가 | 완성도·명확성 점수 및 피드백 |
| `consistency_checker` | 생성 문서 목록 | JSON 이슈 목록 | 교차 참조, 명명 충돌 감지 |
| `coordinator` | 품질·일관성 결과 | 승인/개선 지시 JSON | 승인 여부 및 개선 요청 |

## 4. 컨텍스트 및 도구 상호작용

- `WorkflowContext.project`: FRS 경로, 서비스 유형, 출력 디렉터리 등 프로젝트 전역 정보 보관.
- `WorkflowContext.documents`: 이전 생성 본문과 템플릿 검증 결과 저장.
- `WorkflowContext.metrics`: 템플릿 검사·품질 사이클 등 메트릭 기록.
- `load_frs_document`, `apply_template`, `validate_openapi_spec` 등 도구 함수는 `session_id`를 전달받아 실행 로그를 세션 단위로 수집합니다.
- Git 연동(`create_git_branch`, `commit_changes`)은 옵션이며, 성공 여부에 따라 워크플로우 로그만 남깁니다.

## 5. 실행 결과

1. 순차 생성 성공 → 품질 루프 실행 → 개선 사항 적용 시 다시 저장.
2. 품질 루프가 승인 조건을 충족하면 최종 파일 목록과 실행 시간, 품질 사이클 요약을 반환합니다.
3. 실행 중 예외가 발생하면 저장된 파일 목록과 함께 실패 응답을 제공하여 부분 성공 여부를 알립니다.
