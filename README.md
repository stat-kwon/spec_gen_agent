# Spec Agent 워크플로우 안내

Spec Agent는 FRS(Functional Requirements Specification) 문서를 입력으로 받아 요구사항부터 OpenAPI까지 일련의 산출물을 자동 생성하는 Agentic 워크플로우입니다. 순차 생성 파이프라인과 품질 보강 루프를 결합해 안정성과 자율성을 동시에 확보합니다.

## 주요 기능

- `requirements.md`, `design.md`, `tasks.md`, `changes.md`, `openapi.json(API 한정)`을 순차적으로 생성
- 템플릿 검증(`apply_template`, `validate_openapi_spec`)을 통한 형식 품질 보장
- `QualityImprovementManager`가 품질·일관성 평가 결과에 따라 필요한 문서를 자동 재생성
- Git 브랜치 생성 및 커밋 연계(옵션)
- `flow.md`에 전체 흐름 다이어그램과 상세 설명 제공

## 설치 및 설정

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

환경 변수 설정:

```bash
cp .env.example .env
```

`.env`에 `OPENAI_API_KEY`를 포함해 주세요.

## 사용 방법

```bash
# API 서비스 명세 생성
spec-agent generate specs/FRS-1.md --service-type api

# Web 서비스 명세 생성
spec-agent generate specs/FRS-2.md --service-type web

# 출력 경로 지정
spec-agent generate specs/FRS-1.md --service-type api --output-dir ./output

# Git 워크플로우 생략
spec-agent generate specs/FRS-1.md --service-type api --no-git

# 기존 산출물 검증
spec-agent validate specs/FRS-1/api
```

CLI는 내부적으로 `spec_agent.workflows.get_workflow()`를 통해 `SpecificationWorkflowRunner`를 불러와 실행합니다.

## 워크플로우 개요

- **Sequential Pipeline**: `SequentialDocumentGenerator`가 FRS 로드 → 에이전트 초기화 → 문서 생성 → 템플릿 검증 → 파일 저장을 고정 순서로 수행합니다.
- **Adaptive Quality Loop**: `QualityImprovementManager`가 품질·일관성 에이전트 평가를 통합해 승인 여부를 판단하고, 필요한 문서만 재생성하도록 지시합니다.
- 전체 흐름은 `flow.md`의 Mermaid 다이어그램을 참고하세요.

## 디렉터리 구조

```
spec_agent/
├── agents/            # 문서별 에이전트 팩토리
├── workflows/         # 파이프라인 러너 및 생성/품질 단계 모듈
│   ├── context.py     # WorkflowContext 데이터 구조
│   ├── generation.py  # SequentialDocumentGenerator
│   ├── quality.py     # QualityImprovementManager
│   ├── git_ops.py     # Git 연동 헬퍼
│   └── prompts.py     # 프롬프트 빌더
├── tools/             # 템플릿, 검증, Git 등 도구 함수
├── utils/             # 로깅 등 공통 유틸
├── config.py          # 환경 설정 로더
├── workflow.py        # 기존 경로 호환용 래퍼
└── cli.py             # CLI 엔트리포인트
```

생성된 문서는 기본적으로 `specs/<FRS-ID>/<service-type>/` 경로에 저장됩니다.

## 개발 및 테스트

```bash
# 포맷/테스트 전 의존성 설치
pip install -r requirements.txt

# 전체 테스트 실행
pytest

# 특정 테스트만 실행
pytest tests/test_workflow_templates.py -k quality
```

- 테스트는 `tests/` 하위에 Pytest 스타일로 배치되어 있으며, 에이전트 프롬프트와 검증 로직을 집중적으로 다룹니다.
- 새 에이전트나 템플릿을 추가할 때에는 동일한 스타일의 테스트 시나리오를 추가해 회귀 안전망을 구축해 주세요.

## 참고 자료

- `flow.md`: 전체 워크플로우 다이어그램 및 컨텍스트 설명
- `specs/`: 샘플 FRS 입력과 생성 결과
- `AGENTS.md`, `CLAUDE.md`: 프롬프트 설계 및 Agentic 패턴 참고 문서
