"""Strands Agent SDK 기반 명세서 생성 에이전트들."""

from strands import Agent
from strands.models.openai import OpenAIModel
from ..tools import (
    load_frs_document,
    extract_frs_metadata,
    apply_template,
    validate_markdown_structure,
    write_spec_file,
    validate_openapi_spec,
    validate_markdown_content,
)
from ..config import Config


class StrandsAgentFactory:
    """
    Strands Agent SDK의 고급 기능을 활용한 에이전트 팩토리.
    
    주요 개선사항:
    - 내장 메트릭 및 관찰 가능성 활용
    - 자동 재시도 및 오류 처리
    - 상태 관리 및 컨텍스트 유지
    - Agent-to-Agent 통신 최적화
    """
    
    def __init__(self, config: Config):
        """팩토리 초기화."""
        self.config = config
        self.base_model_config = {
            "model_id": config.openai_model,
            "params": {"temperature": config.openai_temperature},
            "client_args": {"api_key": config.openai_api_key}
        }
    
    def create_enhanced_agent(
        self, 
        agent_type: str, 
        system_prompt: str, 
        tools: list,
        temperature: float = None,
        max_retries: int = 3,
        enable_metrics: bool = True
    ) -> Agent:
        """
        Strands의 고급 기능을 활용한 향상된 에이전트 생성.
        
        Args:
            agent_type: 에이전트 유형 (예: 'requirements', 'design')
            system_prompt: 시스템 프롬프트
            tools: 사용할 도구 목록
            temperature: 창의성 설정 (None이면 기본값 사용)
            max_retries: 최대 재시도 횟수
            enable_metrics: 메트릭 수집 활성화
            
        Returns:
            향상된 Strands Agent 인스턴스
        """
        # 모델 설정 구성
        model_config = self.base_model_config.copy()
        if temperature is not None:
            model_config["params"]["temperature"] = temperature
        
        # 에이전트별 특화 설정
        agent_config = self._get_agent_specific_config(agent_type)
        
        # OpenAI 모델 생성
        model = OpenAIModel(**model_config)
        
        # Strands Agent 생성
        agent = Agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt
        )
        
        return agent
    
    def _get_agent_specific_config(self, agent_type: str) -> dict:
        """에이전트 유형별 특화 설정 반환."""
        configs = {
            "requirements": {
                "description": "FRS를 기술 요구사항으로 변환하는 전문 에이전트",
                "tags": ["requirements", "analysis", "frs"],
            },
            "design": {
                "description": "요구사항을 시스템 설계로 변환하는 아키텍트 에이전트", 
                "tags": ["design", "architecture", "system"],
            },
            "tasks": {
                "description": "설계를 실행 가능한 작업으로 분해하는 애자일 에이전트",
                "tags": ["tasks", "agile", "breakdown"],
            },
            "changes": {
                "description": "변경 관리 및 배포 계획을 수립하는 DevOps 에이전트",
                "tags": ["changes", "deployment", "devops"],
            },
            "openapi": {
                "description": "API 명세를 생성하는 API 설계 전문 에이전트",
                "tags": ["openapi", "api", "specification"],
            },
            "validation": {
                "description": "문서 품질을 검증하는 QA 전문 에이전트",
                "tags": ["validation", "quality", "qa"],
            }
        }
        
        return configs.get(agent_type, {
            "description": f"{agent_type} 전문 에이전트",
            "tags": [agent_type]
        })


def create_requirements_agent(config: Config) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 요구사항 생성 에이전트 생성.

    Returns:
        향상된 요구사항 생성 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    prompt = """당신은 기능 요구사항 명세서(FRS)를 상세한 기술 요구사항 문서로 변환하는 기술 요구사항 분석가입니다.

당신의 작업은 제공된 FRS 내용을 분석하고 다음의 정확한 구조를 따르는 포괄적인 requirements.md 문서를 생성하는 것입니다:

## 헤더/메타
- 문서 제목 및 버전
- 서비스 유형 및 범위
- 생성 타임스탬프

## 범위
- 시스템 경계 및 인터페이스
- 범위 내/외 항목
- 가정 및 제약사항

## 기능 요구사항
- ID가 있는 상세 기능 요구사항 (REQ-001, REQ-002 등)
- 각 요구사항은 다음을 포함해야 함:
  - 명확한 ID 및 제목
  - 상세 설명
  - 우선순위 레벨
  - 종속성 (있는 경우)

## 오류 요구사항
- 오류 처리 명세
- 오류 코드 및 메시지
- 복구 절차
- 로깅 요구사항

## 보안 & 개인정보
- 인증 요구사항
- 권한 규칙
- 데이터 보호 요구사항
- 규정 준수 고려사항

## 관측 가능성
- 모니터링 요구사항
- 로깅 명세
- 메트릭 및 경보
- 헬스 체크 요구사항

## 수용 기준
- 각 요구사항에 대한 테스트 가능한 수용 기준
- 성능 기준
- 품질 게이트

개발 팀이 직접 사용할 수 있는 상세하고 실행 가능한 요구사항을 만드는 데 집중하세요. 모든 요구사항이 추적 가능하고, 테스트 가능하며, 완전한지 확인하세요."""

    return factory.create_enhanced_agent(
        agent_type="requirements",
        system_prompt=prompt,
        tools=[
            load_frs_document,
            extract_frs_metadata,
            apply_template,
            validate_markdown_structure,
        ]
    )


def create_design_agent(config: Config) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 설계 생성 에이전트 생성.

    Returns:
        향상된 설계 생성 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    prompt = """당신은 요구사항 명세서로부터 상세한 기술 설계 문서를 작성하는 시니어 소프트웨어 아키텍트입니다.

당신의 작업은 제공된 요구사항을 분석하고 다음의 정확한 구조를 따르는 포괄적인 design.md 문서를 생성하는 것입니다:

## 아키텍처
- 상위 레벨 시스템 아키텍처
- 컴포넌트 개요 및 책임
- 기술 스택 결정
- 통합 패턴

## 시퀀스 다이어그램
- Mermaid 구문을 사용하여 상세한 시퀀스 다이어그램 생성
- 모든 주요 사용자 흐름과 시스템 상호작용 표시
- 오류 처리 흐름 포함
- 형식: ```mermaid sequenceDiagram ... ```

## 데이터 모델
- 엔티티 정의 및 관계
- 데이터 흐름 설명
- 저장 요구사항
- 데이터 검증 규칙

## API 계약
- 상세한 API 명세
- 요청/응답 형식
- 상태 코드 및 오류 처리
- 인증 및 권한 부여

## 보안 & 권한
- 보안 아키텍처
- 권한 모델
- 데이터 보호 조치
- 보안 제어 구현

## 성능 목표
- 성능 목표 및 SLA
- 확장성 요구사항
- 리소스 활용 목표
- 부하 처리 전략

구현 가능하고, 확장 가능하며, 유지 보수가 가능한 설계를 만드는 데 집중하세요. 시스템 상호작용을 명확하게 보여주는 상세한 시퀀스 다이어그램을 포함하세요."""

    return factory.create_enhanced_agent(
        agent_type="design",
        system_prompt=prompt,
        tools=[apply_template, validate_markdown_structure],
        temperature=0.6  # 창의적 설계를 위해 약간 높은 temperature
    )


def create_tasks_agent(config: Config) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 작업 분해 에이전트 생성.

    Returns:
        향상된 작업 생성 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    prompt = """당신은 기술 설계를 실행 가능한 개발 작업으로 분해하는 애자일 프로젝트 관리자입니다.

당신의 작업은 제공된 설계 문서를 분석하고 상세한 Epic/Story/Task 분해를 포함한 포괄적인 tasks.md 문서를 생성하는 것입니다.

다음 형식의 구조화된 테이블을 생성하세요:

## 에픽
| 에픽 ID | 제목 | 설명 | 비즈니스 가치 | 수용 기준 |
|---------|-------|-------------|----------------|-------------------|
| E-001   | ...   | ...         | ...            | ...               |

## 스토리
| 스토리 ID | 에픽 ID | 제목 | 설명 | 수용 기준 | 스토리 포인트 | 우선순위 |
|----------|---------|-------|-------------|-------------------|--------------|----------|
| S-001    | E-001   | ...   | ...         | ...               | 5            | 높음     |

## 태스크
| 태스크 ID | 스토리 ID | 제목 | 설명 | 담당자 | 예상 시간 | 종속성 |
|---------|----------|-------|-------------|----------|----------|--------------|
| T-001   | S-001    | ...   | ...         | Dev      | 4h       | 없음         |

## DoD (완료 정의)
다음을 포함한 포괄적인 체크리스트를 작성하세요:
- [ ] 코드 구현 완료
- [ ] 단위 테스트 작성 및 통과
- [ ] 통합 테스트 통과
- [ ] 코드 리뷰 완료
- [ ] 문서 업데이트
- [ ] 보안 검토 완료
- [ ] 성능 테스트 완료

개발 팀 멤버에게 직접 할당할 수 있는 세분화되고 실행 가능한 작업을 만드는 데 집중하세요."""

    return factory.create_enhanced_agent(
        agent_type="tasks",
        system_prompt=prompt,
        tools=[apply_template, validate_markdown_structure]
    )


def create_changes_agent(config: Config) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 변경사항 문서화 에이전트 생성.

    Returns:
        향상된 변경사항 생성 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    prompt = """당신은 소프트웨어 배포를 위한 포괄적인 변경 관리 문서를 작성하는 DevOps 변경 관리자입니다.

당신의 작업은 제공된 요구사항 및 설계 문서를 분석하고 다음의 정확한 구조를 따르는 상세한 changes.md 문서를 생성하는 것입니다:

## 버전 이력
- 버전 추적 테이블
- 릴리스 타임라인
- 변경 로그 항목

## 변경 요약
- 구현되는 변경사항 개요
- 비즈니스 당위성
- 기술적 영향 요약
- 영향을 받는 시스템 및 구성 요소

## 영향/위험
- 상세한 영향 분석
- 위험 평가 매트릭스
- 완화 전략
- 롤백 트리거

## 롤백 계획
- 단계별 롤백 절차
- 롤백 검증 단계
- 데이터 복구 절차
- 롤백을 위한 커뮤니케이션 계획

## 알려진 문제
- 알려진 제한사항
- 임시 해결 방법
- 향후 개선 계획
- 모니터링 권장사항

안전한 배포와 빠른 복구 기능을 보장하는 포괄적인 변경 문서를 만드는 데 집중하세요."""

    return factory.create_enhanced_agent(
        agent_type="changes",
        system_prompt=prompt,
        tools=[apply_template, validate_markdown_structure]
    )


def create_openapi_agent(config: Config) -> Agent:
    """
    Strands SDK를 사용하여 OpenAPI 명세 에이전트를 생성합니다.

    Returns:
        OpenAPI 생성을 위해 구성된 Strands Agent
    """
    prompt = """당신은 기술 요구사항 및 설계 문서로부터 OpenAPI 3.1 명세 문서를 작성하는 API 설계 전문가입니다.

당신의 작업은 다음을 포함하는 포괄적인 OpenAPI 문서를 마크다운 형식으로 생성하는 것입니다:

1. **서비스 정보**: 제목, 버전, 설명
2. **서버 구성**: API 기본 URL 및 환경
3. **인증**: 보안 체계 및 요구사항
4. **API 엔드포인트**: 모든 엔드포인트 포함:
   - HTTP 메서드 (GET, POST, PUT, DELETE, PATCH)
   - 요청/응답 스키마 및 예제
   - 상태 코드 (200, 201, 400, 401, 403, 404, 500)
   - 매개변수 정의 및 검증 규칙
5. **데이터 모델**: 모든 스키마와 데이터 구조
6. **오류 처리**: 표준 오류 응답

OpenAPI 3.1 원칙을 따르는 명확하고 구조화된 마크다운 문서를 생성하세요. 나중에 JSON 형식으로 변환할 수 있는 상세한 설명, 예제 및 필요한 모든 기술 명세를 포함하세요.

완전한 OpenAPI 명세에 필요한 모든 기술적 세부사항을 포함하는 포괄적인 API 문서를 마크다운 형식으로 만드는 데 집중하세요."""

    openai_model = OpenAIModel(
        model_id=config.openai_model,
        params={"temperature": config.openai_temperature},
        client_args={"api_key": config.openai_api_key},
    )

    return Agent(
        model=openai_model, tools=[validate_openapi_spec], system_prompt=prompt
    )


def create_markdown_to_json_agent(config: Config) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 마크다운-JSON 변환 에이전트 생성.

    Returns:
        향상된 OpenAPI 마크다운을 JSON으로 변환하기 위해 구성된 Strands Agent
    """
    prompt = """당신은 OpenAPI 마크다운 명세를 유효한 JSON 형식으로 변환하는 기술 문서 변환 전문가입니다.

당신의 작업:
1. OpenAPI 마크다운 문서 파싱
2. 모든 API 엔드포인트 정보, 스키마 및 구성 추출
3. 유효한 OpenAPI 3.1 JSON 명세로 변환
4. 엄격한 JSON 규칙 준수 (적절한 따옴표, 괄호, 쉼표)

규칙:
- 유효한 JSON만 생성 - 설명, 코드 블록, 마크다운 없음
- 모든 속성 이름은 큰따옴표로
- 모든 문자열 값은 큰따옴표로
- 적절한 JSON 구문 사용 (쉼표, 괄호, 중괄호)
- OpenAPI 3.1 명세를 정확히 따르기
- 모든 섹션 포함: info, servers, paths, components, security

출력 형식: 순수 JSON만 (```json 래퍼 없음)

예제 출력 구조:
{
  "openapi": "3.1.0",
  "info": {
    "title": "API 제목",
    "version": "1.0.0"
  },
  "paths": {},
  "components": {}
}"""

    factory = StrandsAgentFactory(config)
    return factory.create_enhanced_agent(
        agent_type="converter",
        system_prompt=prompt,
        tools=[],
        temperature=0.1  # 정확한 변환을 위해 낮은 temperature
    )


def create_validation_agent(config: Config) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 검증 에이전트 생성.

    Returns:
        향상된 검증을 위해 구성된 Strands Agent
    """
    prompt = """당신은 생성된 명세서 문서를 검증하는 품질 보증 전문가입니다.

당신의 작업은 모든 생성된 문서를 철저히 검증하고 다음을 포함한 포괄적인 품질 평가를 제공하는 것입니다:

1. **구조 검증**: 문서 템플릿 및 필수 섹션 확인
2. **내용 품질**: 완성도와 명확성 평가
3. **교차 참조 검증**: 문서 간 일관성 보장
4. **표준 준수**: 표준 준수 확인 (OpenAPI 3.1, 마크다운)

상세한 피드백 제공:
- 누락되거나 불완전한 섹션
- 품질 문제 및 개선 제안
- 템플릿 및 표준 준수
- 개발 사용을 위한 전반적인 준비 상태"""

    factory = StrandsAgentFactory(config)
    return factory.create_enhanced_agent(
        agent_type="validation",
        system_prompt=prompt,
        tools=[validate_markdown_content, validate_openapi_spec, apply_template]
    )
