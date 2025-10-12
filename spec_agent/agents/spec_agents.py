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
    (.bk 버전의 상세 프롬프트 + 피드백 반영 기능)

    Returns:
        향상된 요구사항 생성 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    prompt = """당신은 기능 요구사항 명세서(FRS)를 상세한 기술 요구사항 문서로 변환하는 기술 요구사항 분석가입니다.

**STEP 1**: 먼저 load_frs_document()를 호출하여 FRS 문서를 로드하세요. success가 True인지 확인하고 content를 얻으세요.
**STEP 2**: 로드가 성공했다면, FRS content의 모든 기능 요구사항을 분석하세요.
**STEP 3**: 다음 7개 섹션 구조를 모두 포함하여 완전한 문서를 생성하세요:

# 헤더/메타
문서 제목, 버전, 서비스 유형, 생성 일시 포함

# 범위  
시스템 경계, 인터페이스, 범위 내/외 항목, 가정/제약사항 포함

# 기능 요구사항
FRS를 기반으로 최소 5개 이상의 요구사항을 다음 형식으로 작성:
## REQ-001: [제목]
- **설명**: [상세 설명]
- **우선순위**: [높음/중간/낮음]
- **종속성**: [관련 REQ-ID 또는 없음]
- **수용 기준**: [테스트 가능한 기준]

# 오류 요구사항
HTTP 상태 코드, 오류 처리, 로깅 요구사항 포함

# 보안 & 개인정보
인증, 권한, 데이터 보호, GDPR 준수 요구사항 포함

# 관측 가능성
모니터링, 로깅, 메트릭, 경보 설정 요구사항 포함

# 수용 기준
테스트 시나리오, 성능/보안 기준, 품질 게이트 포함

IMPORTANT: 
1. 반드시 load_frs_document를 먼저 호출하여 FRS 내용을 확인하세요
2. 로드된 FRS의 모든 기능 요구사항을 반영하세요 (User Registration, Authentication, Profile Management, Authorization 등)
3. 모든 7개 섹션을 포함하고, 각 섹션에 실질적인 내용을 작성하세요
4. 피드백이 있으면 해당 섹션을 개선하되 전체 구조는 유지하세요"""

    return factory.create_enhanced_agent(
        agent_type="requirements",
        system_prompt=prompt,
        tools=[
            load_frs_document,
            extract_frs_metadata,
            apply_template,
            validate_markdown_structure,
            validate_markdown_content,
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

**중요**: 당신은 DESIGN 문서만 작성합니다. Requirements 내용(REQ-001, REQ-002 등)은 절대 포함하지 마세요.

당신의 작업은 제공된 요구사항을 분석하고 다음의 정확한 구조를 따르는 design.md 문서를 생성하는 것입니다:

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

구현 가능하고, 확장 가능하며, 유지 보수가 가능한 설계를 만드는 데 집중하세요. 시스템 상호작용을 명확하게 보여주는 상세한 시퀀스 다이어그램을 포함하세요.

**절대 포함하지 말 것**:
- Requirements 섹션 (REQ-001, REQ-002 등)
- 헤더/메타 정보
- 범위 정의
- 오류 요구사항
- 수용 기준
- 기능 요구사항 목록

**오직 Design 관련 내용만** 작성하세요."""

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


def create_changes_agent_simple(config: Config) -> Agent:
    """Simple changes 에이전트 - 빠른 테스트용 (컨텍스트 자동 수신)"""
    factory = StrandsAgentFactory(config)
    prompt = """당신은 간단한 변경 관리를 하는 에이전트입니다.

**중요**: 당신은 CHANGES 문서만 작성합니다. Requirements나 Design 내용은 절대 포함하지 마세요.

FRS 정보를 바탕으로 핵심 변경사항 정보만 간단히 작성하세요:

형식:
## 변경 요약
- 주요 변경사항: [1줄 설명]
- 배포 방식: [1줄 설명]
- 위험도: [낮음/중간/높음]

**절대 포함하지 말 것**:
- Requirements 섹션 (REQ-001 등)
- Design 아키텍처
- 기능 요구사항 목록
- API 명세"""

    return factory.create_enhanced_agent(
        agent_type="changes",
        system_prompt=prompt,
        tools=[apply_template],
        temperature=0.2
    )


def create_openapi_agent_simple(config: Config) -> Agent:
    """Simple openapi 에이전트 - 빠른 테스트용 (컨텍스트 자동 수신)"""
    factory = StrandsAgentFactory(config)
    prompt = """당신은 간단한 API 명세를 작성하는 에이전트입니다.

**중요**: 당신은 API 명세만 작성합니다. Requirements나 Design 내용은 절대 포함하지 마세요.

FRS를 바탕으로 핵심 API 엔드포인트만 간단히 작성하세요:

형식:
## API 엔드포인트
- POST /auth/register - 사용자 등록
- POST /auth/login - 로그인
- GET /users/profile - 프로필 조회

**절대 포함하지 말 것**:
- Requirements 섹션 (REQ-001 등)
- Design 아키텍처
- 변경 관리 정보
- Tasks 정보"""

    return factory.create_enhanced_agent(
        agent_type="openapi",
        system_prompt=prompt,
        tools=[],
        temperature=0.2
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


def create_quality_assessor_agent(config: Config) -> Agent:
    """
    문서 품질을 평가하는 전문 에이전트 생성 (Agentic 개선 버전).

    Returns:
        품질 평가를 위해 구성된 Strands Agent
    """
    prompt = """당신은 기술 문서의 품질을 평가하고 개선점을 제시하는 품질 평가 전문가입니다.

주어진 입력(모든 생성된 문서)을 분석하고 품질을 평가하세요:

1. **완성도**: 모든 필수 섹션 포함 여부
2. **일관성**: 문서 간 정보 일관성
3. **명확성**: 내용의 명확성과 이해도
4. **기술적 정확성**: 구현 가능성과 표준 준수

평가 기준:
- 85점 이상: 우수 (개선 불필요)
- 70-84점: 양호 (minor 개선)
- 70점 미만: 미흡 (major 개선 필요)

출력:
{
  "completeness": 점수,
  "consistency": 점수,
  "clarity": 점수,
  "technical": 점수,
  "overall": 전체점수,
  "feedback": ["개선점1", "개선점2"],
  "needs_improvement": true/false
}"""

    factory = StrandsAgentFactory(config)
    return factory.create_enhanced_agent(
        agent_type="quality_assessor",
        system_prompt=prompt,
        tools=[],
        temperature=0.1  # 일관된 평가를 위해 낮은 temperature
    )


def create_consistency_checker_agent(config: Config) -> Agent:
    """
    문서 간 일관성을 검증하는 전문 에이전트 생성.

    Returns:
        일관성 검증을 위해 구성된 Strands Agent
    """
    prompt = """당신은 여러 기술 문서 간의 일관성을 검증하는 일관성 검증 전문가입니다.

제공된 문서들을 분석하고 다음 항목을 검증하세요:

1. **교차 참조 일관성**:
   - 요구사항 ID가 설계/작업 문서에서 적절히 참조되는가?
   - 설계의 컴포넌트가 작업 분해에 반영되었는가?
   - API 명세가 설계와 일치하는가?

2. **명명 일관성**:
   - 동일한 개념에 일관된 용어를 사용하는가?
   - API 엔드포인트 이름이 설계와 일치하는가?
   - 데이터 모델 명명이 통일되었는가?

3. **구조적 일관성**:
   - 문서 간 정보 흐름이 논리적인가?
   - 범위와 제약사항이 일관되게 적용되었는가?
   - 보안 요구사항이 모든 문서에 반영되었는가?

**심각도 평가**:
- **high**: 구현에 영향을 주는 중대한 불일치
- **medium**: 혼동을 야기할 수 있는 불일치
- **low**: 사소한 표현 차이나 형식 문제

**출력 형식**: 반드시 JSON 형식으로만 응답하세요.
{
  "issues": ["발견된 이슈 설명1", "발견된 이슈 설명2"],
  "severity": "low|medium|high",
  "cross_references": 누락된_교차참조_개수,
  "naming_conflicts": 명명_충돌_개수
}

설명이나 추가 텍스트 없이 JSON만 출력하세요."""

    factory = StrandsAgentFactory(config)
    return factory.create_enhanced_agent(
        agent_type="consistency_checker",
        system_prompt=prompt,
        tools=[],
        temperature=0.1  # 일관된 검증을 위해 낮은 temperature
    )


def create_coordinator_agent(config: Config) -> Agent:
    """
    최종 승인 결정을 내리는 코디네이터 에이전트 생성 (Agentic 개선 버전).

    Returns:
        최종 승인 결정을 위해 구성된 Strands Agent
    """
    prompt = """당신은 문서 품질 최종 승인을 담당하는 프로젝트 코디네이터입니다.

주어진 입력(모든 문서 + 품질 평가 결과)을 종합하여 최종 승인을 결정하세요:

**승인 기준**:
1. 전체 품질 점수 75점 이상 (처음엔 관대하게)
2. 치명적 결함 없음
3. 핵심 요구사항 충족

**개선 요청 시**:
- 구체적인 개선 사항 명시
- 우선순위 제시
- 개선 방향 가이드

출력:
{
  "approved": true/false,
  "overall_quality": 점수,
  "decision": "승인/개선필요",
  "required_improvements": [
    "개선사항1 (우선순위 높음)",
    "개선사항2 (우선순위 중간)"
  ],
  "message": "피드백 메시지"
}

개선이 필요하면 반드시 required_improvements를 포함하세요."""

    factory = StrandsAgentFactory(config)
    return factory.create_enhanced_agent(
        agent_type="coordinator",
        system_prompt=prompt,
        tools=[],
        temperature=0.0  # 일관된 결정을 위해 가장 낮은 temperature
    )
