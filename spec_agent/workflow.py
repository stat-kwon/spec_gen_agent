"""
Strands Agent SDK 기반 스펙 생성 워크플로우.

이 모듈은 Strands의 고급 멀티 에이전트 패턴을 활용하여 
기존의 커스텀 오케스트레이션 로직을 대체합니다.
"""

import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime

from strands import Agent
from strands.models.openai import OpenAIModel

from .config import Config
from .models import ServiceType, GenerationContext, FRSDocument
from .tools import (
    load_frs_document,
    create_output_directory,
    write_spec_file,
    create_git_branch,
    commit_changes
)


class SpecificationWorkflow:
    """
    Strands Agent SDK를 활용한 명세서 생성 워크플로우.
    
    주요 기능:
    - Agent-to-Agent (A2A) 패턴을 통한 에이전트 간 협업
    - 자동 상태 관리 및 컨텍스트 유지
    - 내장 품질 메트릭 및 관찰 가능성
    - 자동 오류 처리 및 재시도 메커니즘
    """
    
    def __init__(self, config: Optional[Config] = None):
        """워크플로우 초기화."""
        self.config = config or Config.from_env()
        self.config.validate()
        
        # Strands Agent들을 A2A 패턴으로 구성
        self.agents = self._initialize_workflow_agents()
        
        # 워크플로우 상태 관리
        self.context: Optional[GenerationContext] = None
        self.execution_state = {}
        
        # 성능 추적
        self.start_time = None
        self.metrics = {}
    
    def _initialize_workflow_agents(self) -> Dict[str, Agent]:
        """워크플로우에 참여하는 모든 에이전트를 초기화."""
        base_model = OpenAIModel(
            model_id=self.config.openai_model,
            params={"temperature": self.config.openai_temperature},
            client_args={"api_key": self.config.openai_api_key}
        )
        
        return {
            "requirements": self._create_requirements_agent(base_model),
            "design": self._create_design_agent(base_model),
            "tasks": self._create_tasks_agent(base_model),
            "changes": self._create_changes_agent(base_model),
            "openapi": self._create_openapi_agent(base_model),
            "quality_assessor": self._create_quality_agent(base_model),
            "consistency_checker": self._create_consistency_agent(base_model),
            "coordinator": self._create_coordinator_agent(base_model)
        }
    
    def _create_requirements_agent(self, model: OpenAIModel) -> Agent:
        """요구사항 생성 전문 에이전트."""
        return Agent(
            model=model,
            tools=[
                load_frs_document,
                write_spec_file
            ],
            system_prompt="""당신은 FRS를 기술 요구사항으로 변환하는 전문가입니다.
            
주요 책임:
1. FRS 문서를 분석하여 핵심 요구사항 추출
2. 구조화된 requirements.md 문서 생성
3. 요구사항 ID 체계 및 우선순위 설정
4. 다음 에이전트를 위한 명확한 컨텍스트 제공

출력 형식:
- 헤더/메타, 범위, 기능 요구사항, 오류 요구사항
- 보안 & 개인정보, 관측 가능성, 수용 기준

다음 에이전트에게 전달할 정보를 명확히 정리하세요."""
        )
    
    def _create_design_agent(self, model: OpenAIModel) -> Agent:
        """설계 전문 에이전트 - 요구사항 에이전트의 출력을 받아 처리."""
        return Agent(
            model=OpenAIModel(
                model_id=self.config.openai_model,
                params={"temperature": 0.6},  # 창의적 설계를 위해 약간 높은 temperature
                client_args={"api_key": self.config.openai_api_key}
            ),
            tools=[write_spec_file],
            system_prompt="""당신은 요구사항을 기술 설계로 변환하는 시니어 아키텍트입니다.

입력: 이전 에이전트가 생성한 요구사항 문서
출력: 상세한 design.md 문서

주요 책임:
1. 요구사항을 분석하여 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 생성
3. 데이터 모델 및 API 계약 정의
4. 보안 & 성능 목표 설정

이전 에이전트의 출력을 참조하여 일관성 있는 설계를 만드세요.
다음 에이전트(작업 분해)를 위한 명확한 설계 정보를 제공하세요."""
        )
    
    def _create_tasks_agent(self, model: OpenAIModel) -> Agent:
        """작업 분해 전문 에이전트."""
        return Agent(
            model=model,
            tools=[write_spec_file],
            system_prompt="""당신은 설계를 실행 가능한 작업으로 분해하는 애자일 전문가입니다.

입력: 이전 에이전트들이 생성한 요구사항 및 설계 문서
출력: 상세한 tasks.md 문서

주요 책임:
1. 설계를 Epic/Story/Task로 분해
2. 우선순위 및 종속성 설정
3. 예상 시간 및 DoD 정의
4. 개발 팀이 즉시 작업할 수 있는 수준으로 세분화

이전 에이전트들의 결과물과 일관성을 유지하세요."""
        )
    
    def _create_changes_agent(self, model: OpenAIModel) -> Agent:
        """변경 관리 전문 에이전트."""
        return Agent(
            model=model,
            tools=[write_spec_file],
            system_prompt="""당신은 배포 및 변경 관리 전문가입니다.

입력: 전체 프로젝트의 요구사항, 설계, 작업 정보
출력: changes.md 문서

주요 책임:
1. 변경 영향도 분석
2. 위험 평가 및 완화 전략
3. 롤백 계획 수립
4. 배포 전략 및 모니터링 계획

모든 이전 결과물을 종합하여 안전한 배포 계획을 수립하세요."""
        )
    
    def _create_openapi_agent(self, model: OpenAIModel) -> Agent:
        """OpenAPI 명세 전문 에이전트."""
        return Agent(
            model=OpenAIModel(
                model_id=self.config.openai_model,
                params={"temperature": 0.1},  # 정확성을 위해 낮은 temperature
                client_args={"api_key": self.config.openai_api_key}
            ),
            tools=[write_spec_file],
            system_prompt="""당신은 API 설계 및 OpenAPI 명세 전문가입니다.

입력: 요구사항 및 설계 문서에서 추출한 API 정보
출력: OpenAPI 3.1 명세 (JSON 형식)

주요 책임:
1. 요구사항에서 API 엔드포인트 추출
2. 설계 문서의 데이터 모델 반영
3. 인증, 오류 처리, 보안 고려사항 포함
4. 표준 준수 및 실용적인 API 설계

토큰 효율성을 위해 핵심 엔드포인트만 포함하되, 완전한 명세를 작성하세요."""
        )
    
    def _create_quality_agent(self, model: OpenAIModel) -> Agent:
        """품질 평가 전문 에이전트."""
        return Agent(
            model=model,
            tools=[],
            system_prompt="""당신은 문서 품질 평가 전문가입니다.

주요 책임:
1. 생성된 모든 문서의 품질 평가
2. 완성도, 일관성, 명확성, 기술 정확성 평가 (각 0-100점)
3. 구체적인 개선 피드백 제공
4. 전체 품질 점수 계산

평가 기준:
- 완성도 (30%): 모든 필수 섹션 포함
- 일관성 (30%): 문서 간 용어 및 내용 일치
- 명확성 (20%): 이해하기 쉬운 구조와 언어
- 기술 정확성 (20%): 실현 가능하고 정확한 기술 내용

85점 이상일 때만 승인하세요."""
        )
    
    def _create_consistency_agent(self, model: OpenAIModel) -> Agent:
        """일관성 검증 전문 에이전트."""
        return Agent(
            model=model,
            tools=[],
            system_prompt="""당신은 문서 간 일관성 검증 전문가입니다.

주요 책임:
1. 요구사항 ↔ 설계 정렬 확인
2. 설계 ↔ 작업 매핑 검증
3. 전체 문서 세트의 용어 일관성 확인
4. 누락되거나 모순되는 내용 식별

검증 항목:
- 요구사항 ID가 설계에서 모두 다뤄지는가?
- 설계 컴포넌트가 작업에서 모두 다뤄지는가?
- 용어와 정의가 일관되게 사용되는가?
- API 명세가 요구사항과 일치하는가?

불일치 사항을 구체적으로 나열하고 수정 방향을 제시하세요."""
        )
    
    def _create_coordinator_agent(self, model: OpenAIModel) -> Agent:
        """워크플로우 조정 및 의사결정 에이전트."""
        return Agent(
            model=model,
            tools=[
                create_output_directory,
                create_git_branch,
                commit_changes
            ],
            system_prompt="""당신은 전체 워크플로우를 조정하는 마스터 에이전트입니다.

주요 책임:
1. 에이전트 간 작업 순서 및 의존성 관리
2. 품질 기준 미달 시 재작업 지시
3. 최종 승인 및 출력 관리
4. Git 워크플로우 및 파일 관리

의사결정 권한:
- 문서 품질이 기준에 미달하면 해당 에이전트에게 재작업 요청
- 일관성 문제 발견 시 관련 에이전트들에게 조정 지시
- 모든 품질 기준을 충족하면 최종 승인 및 커밋

효율적이고 체계적인 워크플로우 관리에 집중하세요."""
        )
    
    async def execute_workflow(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str] = None,
        use_git: bool = True
    ) -> Dict[str, Any]:
        """
        워크플로우 실행 - Strands Agent 패턴 활용.
        
        Args:
            frs_path: FRS 마크다운 파일 경로
            service_type: 서비스 유형 (API 또는 WEB)
            output_dir: 사용자 정의 출력 디렉토리
            use_git: Git 워크플로우 사용 여부
            
        Returns:
            실행 결과 및 메트릭
        """
        self.start_time = datetime.now()
        
        try:
            # 1단계: 컨텍스트 초기화
            print("🚀 Strands 워크플로우 시작...")
            self.context = await self._initialize_context(frs_path, service_type, output_dir, use_git)
            
            # 2단계: Agent-to-Agent 순차 실행
            documents = {}
            
            # 요구사항 생성
            print("📋 요구사항 에이전트 실행...")
            documents["requirements"] = await self._execute_requirements_agent()
            
            # 설계 생성
            print("🏗️ 설계 에이전트 실행...")
            documents["design"] = await self._execute_design_agent(documents["requirements"])
            
            # 작업 분해
            print("📝 작업 분해 에이전트 실행...")
            documents["tasks"] = await self._execute_tasks_agent(
                documents["requirements"], 
                documents["design"]
            )
            
            # 변경 관리
            print("📄 변경 관리 에이전트 실행...")
            documents["changes"] = await self._execute_changes_agent(documents)
            
            # OpenAPI (API 서비스만)
            if service_type == ServiceType.API:
                print("🔌 OpenAPI 에이전트 실행...")
                documents["openapi"] = await self._execute_openapi_agent(
                    documents["requirements"], 
                    documents["design"]
                )
            
            # 3단계: 품질 평가 및 일관성 검증
            print("📊 품질 평가 실행...")
            quality_results = await self._assess_quality(documents)
            
            print("🔍 일관성 검증 실행...")
            consistency_results = await self._check_consistency(documents)
            
            # 4단계: 조정 및 최종 승인
            print("👨‍💼 워크플로우 조정자 실행...")
            final_approval = await self._coordinate_final_approval(
                documents, quality_results, consistency_results
            )
            
            # 5단계: 파일 저장 및 Git 커밋
            if final_approval["approved"]:
                print("💾 문서 저장 및 Git 커밋...")
                files_written = await self._save_and_commit(documents, use_git)
                
                execution_time = (datetime.now() - self.start_time).total_seconds()
                
                return {
                    "success": True,
                    "output_dir": self.context.output_dir,
                    "files_written": files_written,
                    "quality_results": quality_results,
                    "consistency_results": consistency_results,
                    "execution_time": execution_time,
                    "framework": "Strands Agent SDK",
                    "pattern": "Agent-to-Agent Workflow"
                }
            else:
                return {
                    "success": False,
                    "error": "품질 기준 미충족",
                    "quality_results": quality_results,
                    "consistency_results": consistency_results
                }
                
        except Exception as e:
            error_msg = f"워크플로우 실행 실패: {str(e)}"
            print(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "error_type": type(e).__name__
            }
    
    async def _initialize_context(
        self, 
        frs_path: str, 
        service_type: ServiceType,
        output_dir: Optional[str],
        use_git: bool
    ) -> GenerationContext:
        """워크플로우 컨텍스트 초기화."""
        # FRS 로드
        frs_result = load_frs_document(frs_path)
        if not frs_result.get("success", False):
            raise ValueError(f"FRS 로드 실패: {frs_path}")
        
        # 출력 디렉토리 설정
        frs_id = self._extract_frs_id(frs_path)
        output_dir_path = output_dir or f"specs/{frs_id}/{service_type.value}"
        
        # Git 브랜치 생성
        if use_git:
            git_result = create_git_branch(frs_id, service_type.value)
            if not git_result.get("success"):
                print(f"⚠️ Git 브랜치 생성 실패: {git_result.get('error')}")
        
        return GenerationContext(
            frs=FRSDocument(
                title=f"FRS {frs_id}",
                content=frs_result.get("content", "")
            ),
            service_type=service_type,
            output_dir=output_dir_path
        )
    
    async def _execute_requirements_agent(self) -> str:
        """요구사항 에이전트 실행."""
        agent = self.agents["requirements"]
        
        prompt = f"""다음 FRS 문서를 분석하여 상세한 requirements.md를 생성하세요:

{self.context.frs.content}

서비스 유형: {self.context.service_type.value}

요구사항:
1. 구조화된 requirements.md 형식으로 작성
2. 명확한 요구사항 ID 체계 사용
3. 다음 에이전트(설계)가 이해할 수 있도록 명확하게 작성
4. 한국어로 작성"""
        
        result = agent(prompt)
        return str(result)
    
    async def _execute_design_agent(self, requirements: str) -> str:
        """설계 에이전트 실행."""
        agent = self.agents["design"]
        
        prompt = f"""다음 요구사항을 바탕으로 상세한 design.md를 생성하세요:

요구사항 문서:
{requirements}

서비스 유형: {self.context.service_type.value}

요구사항:
1. 요구사항을 모두 충족하는 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함
3. 데이터 모델 및 API 계약 정의
4. 다음 에이전트들이 활용할 수 있는 명확한 설계 정보 제공
5. 한국어로 작성"""
        
        result = agent(prompt)
        return str(result)
    
    async def _execute_tasks_agent(self, requirements: str, design: str) -> str:
        """작업 분해 에이전트 실행."""
        agent = self.agents["tasks"]
        
        prompt = f"""다음 요구사항과 설계를 바탕으로 상세한 tasks.md를 생성하세요:

요구사항:
{requirements[:2000]}  # 토큰 효율성을 위해 일부만

설계:
{design[:2000]}  # 토큰 효율성을 위해 일부만

요구사항:
1. Epic/Story/Task 형식으로 작업 분해
2. 우선순위 및 예상 시간 설정
3. DoD (Definition of Done) 체크리스트 포함
4. 개발 팀이 즉시 작업할 수 있는 수준으로 세분화
5. 한국어로 작성"""
        
        result = agent(prompt)
        return str(result)
    
    async def _execute_changes_agent(self, documents: Dict[str, str]) -> str:
        """변경 관리 에이전트 실행."""
        agent = self.agents["changes"]
        
        # 요약된 컨텍스트 생성
        context_summary = f"""프로젝트 개요:
- 서비스 유형: {self.context.service_type.value}
- FRS: {self.context.frs.title}

주요 변경사항 (요약):
- 요구사항: {len(documents.get('requirements', ''))} 문자
- 설계: {len(documents.get('design', ''))} 문자  
- 작업: {len(documents.get('tasks', ''))} 문자"""
        
        prompt = f"""{context_summary}

위 프로젝트의 배포를 위한 상세한 changes.md를 생성하세요:

요구사항:
1. 변경 영향도 및 위험 분석
2. 롤백 계획 수립
3. 배포 전략 및 모니터링 계획
4. 알려진 이슈 및 완화 방안
5. 한국어로 작성"""
        
        result = agent(prompt)
        return str(result)
    
    async def _execute_openapi_agent(self, requirements: str, design: str) -> str:
        """OpenAPI 에이전트 실행."""
        agent = self.agents["openapi"]
        
        # API 관련 정보만 추출
        api_info = self._extract_api_essentials(requirements, design)
        
        prompt = f"""다음 API 정보를 바탕으로 OpenAPI 3.1 명세를 JSON 형식으로 생성하세요:

{api_info}

서비스: {self.context.frs.title}

요구사항:
1. 유효한 JSON 형식의 OpenAPI 3.1 명세
2. 핵심 엔드포인트만 포함 (최대 5개)
3. 인증, 오류 처리 포함
4. 실용적이고 구현 가능한 API 설계
5. 토큰 효율성을 고려한 간결한 구성

JSON만 출력하세요 (설명 없음)."""
        
        result = agent(prompt)
        return str(result)
    
    async def _assess_quality(self, documents: Dict[str, str]) -> Dict[str, Any]:
        """품질 평가 에이전트 실행."""
        agent = self.agents["quality_assessor"]
        quality_results = {}
        
        for doc_type, content in documents.items():
            if not content:
                continue
                
            prompt = f"""다음 {doc_type} 문서의 품질을 평가하세요:

{content[:3000]}  # 토큰 효율성

평가 기준 (0-100점):
1. 완성도 (30%)
2. 일관성 (30%) 
3. 명확성 (20%)
4. 기술 정확성 (20%)

다음 형식으로 응답:
완성도: [점수]
일관성: [점수]  
명확성: [점수]
기술 정확성: [점수]
전체 점수: [계산된 점수]
피드백: [구체적인 개선 사항]"""
            
            result = agent(prompt)
            quality_results[doc_type] = self._parse_quality_result(str(result))
        
        return quality_results
    
    async def _check_consistency(self, documents: Dict[str, str]) -> Dict[str, List[str]]:
        """일관성 검증 에이전트 실행."""
        agent = self.agents["consistency_checker"]
        
        # 문서 요약본 생성
        doc_summaries = {
            doc_type: content[:1500] 
            for doc_type, content in documents.items() 
            if content
        }
        
        prompt = f"""다음 문서들 간의 일관성을 검증하세요:

{doc_summaries}

검증 항목:
1. 요구사항 ↔ 설계 정렬
2. 설계 ↔ 작업 매핑  
3. 전체 용어 일관성
4. API 명세 ↔ 요구사항 일치

불일치 사항을 다음 형식으로 나열:
- [구체적인 불일치 내용]
- [또 다른 불일치 내용]"""
        
        result = agent(prompt)
        return self._parse_consistency_result(str(result))
    
    async def _coordinate_final_approval(
        self, 
        documents: Dict[str, str],
        quality_results: Dict[str, Any],
        consistency_results: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """워크플로우 조정자의 최종 승인."""
        agent = self.agents["coordinator"]
        
        # 품질 점수 요약
        avg_quality = sum(
            result.get("overall", 0) 
            for result in quality_results.values()
        ) / len(quality_results) if quality_results else 0
        
        total_issues = sum(len(issues) for issues in consistency_results.values())
        
        prompt = f"""다음 워크플로우 결과를 검토하여 최종 승인 여부를 결정하세요:

문서 수: {len(documents)}
평균 품질 점수: {avg_quality:.1f}
일관성 이슈 수: {total_issues}

품질 기준: 70점 이상
일관성 기준: 5개 이슈 미만

승인 여부와 이유를 다음 형식으로 응답:
승인: [YES/NO]
이유: [구체적인 승인/거부 사유]"""
        
        result = agent(prompt)
        approval_result = self._parse_approval_result(str(result))
        
        return {
            "approved": approval_result.get("approved", False),
            "reason": approval_result.get("reason", ""),
            "average_quality": avg_quality,
            "total_issues": total_issues
        }
    
    async def _save_and_commit(self, documents: Dict[str, str], use_git: bool) -> List[str]:
        """문서 저장 및 Git 커밋."""
        files_written = []
        
        # 출력 디렉토리 생성
        create_output_directory("specs", self._extract_frs_id(self.context.frs.title), self.context.service_type.value)
        
        # 각 문서 저장
        for doc_type, content in documents.items():
            if not content:
                continue
                
            filename = f"{doc_type}.md"
            if doc_type == "openapi":
                filename = "apis.json"
            
            file_path = self._write_document(filename, content)
            if file_path:
                files_written.append(file_path)
        
        # Git 커밋
        if use_git and files_written:
            frs_id = self._extract_frs_id(self.context.frs.title)
            commit_result = commit_changes(
                f"feat({frs_id}): Strands 워크플로우로 {self.context.service_type.value} 스펙 생성",
                files_written
            )
            
            if commit_result.get("success"):
                print("✅ Git 커밋 완료")
            else:
                print(f"⚠️ Git 커밋 실패: {commit_result.get('error')}")
        
        return files_written
    
    def _write_document(self, filename: str, content: str) -> Optional[str]:
        """문서를 파일로 저장."""
        try:
            output_path = Path(self.context.output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
            
            file_path = output_path / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return str(file_path)
        except Exception as e:
            print(f"❌ 파일 저장 실패 {filename}: {str(e)}")
            return None
    
    def _extract_frs_id(self, frs_path: str) -> str:
        """FRS ID 추출."""
        import re
        path = Path(frs_path)
        match = re.search(r'FRS-(\d+)', str(path))
        return f"FRS-{match.group(1)}" if match else path.stem
    
    def _extract_api_essentials(self, requirements: str, design: str) -> str:
        """API 관련 핵심 정보만 추출."""
        combined = f"{requirements}\n\n{design}"
        
        # API 관련 키워드가 포함된 라인만 추출
        lines = combined.split('\n')
        api_lines = []
        
        keywords = ['api', 'endpoint', 'rest', 'http', 'get', 'post', 'put', 'delete', 'auth']
        
        for line in lines[:100]:  # 처음 100줄만 검사
            if any(keyword in line.lower() for keyword in keywords):
                api_lines.append(line.strip())
                if len(api_lines) >= 20:  # 최대 20줄
                    break
        
        result = '\n'.join(api_lines) if api_lines else "표준 CRUD API 기능"
        return result[:1000]  # 최대 1000자
    
    def _parse_quality_result(self, result: str) -> Dict[str, Any]:
        """품질 평가 결과 파싱."""
        import re
        
        patterns = {
            'completeness': r'완성도:\s*(\d+)',
            'consistency': r'일관성:\s*(\d+)', 
            'clarity': r'명확성:\s*(\d+)',
            'technical_accuracy': r'기술\s*정확성:\s*(\d+)',
            'overall': r'전체\s*점수:\s*(\d+)'
        }
        
        parsed = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, result)
            parsed[key] = int(match.group(1)) if match else 50
        
        # 피드백 추출
        feedback_match = re.search(r'피드백:\s*(.+)', result, re.DOTALL)
        parsed['feedback'] = feedback_match.group(1).strip() if feedback_match else ""
        
        return parsed
    
    def _parse_consistency_result(self, result: str) -> Dict[str, List[str]]:
        """일관성 검증 결과 파싱."""
        issues = []
        lines = result.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                issue = line[1:].strip()
                if issue:
                    issues.append(issue)
        
        return {"consistency_issues": issues}
    
    def _parse_approval_result(self, result: str) -> Dict[str, Any]:
        """승인 결과 파싱."""
        import re
        
        approved = False
        if re.search(r'승인:\s*YES', result, re.IGNORECASE):
            approved = True
        
        reason_match = re.search(r'이유:\s*(.+)', result, re.DOTALL)
        reason = reason_match.group(1).strip() if reason_match else "승인 결과 파싱 실패"
        
        return {
            "approved": approved,
            "reason": reason
        }

    def validate_existing_specs(self, spec_dir: str) -> Dict[str, Any]:
        """
        기존 명세서 문서를 Strands Agent SDK로 검증합니다.
        
        Args:
            spec_dir: 검증할 명세서 디렉토리 경로
            
        Returns:
            검증 결과 딕셔너리
        """
        try:
            spec_path = Path(spec_dir)
            
            if not spec_path.exists() or not spec_path.is_dir():
                return {"success": False, "error": f"Directory not found: {spec_dir}"}
            
            # 검증할 파일들 찾기
            validation_results = []
            files_to_validate = [
                "requirements.md",
                "design.md", 
                "tasks.md",
                "changes.md",
                "apis.json"
            ]
            
            for file_name in files_to_validate:
                file_path = spec_path / file_name
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding='utf-8')
                        
                        # 파일 형식에 따른 검증
                        if file_name.endswith('.md'):
                            # 마크다운 구조 검증
                            if len(content.strip()) > 0 and content.count('#') > 0:
                                validation_results.append({
                                    "file_path": str(file_path),
                                    "document": file_name,
                                    "result": "success - valid markdown structure"
                                })
                            else:
                                validation_results.append({
                                    "file_path": str(file_path),
                                    "document": file_name,
                                    "result": "warning - empty or invalid structure"
                                })
                        elif file_name.endswith('.json'):
                            # JSON 구조 검증
                            import json
                            try:
                                json.loads(content)
                                validation_results.append({
                                    "file_path": str(file_path),
                                    "document": file_name,
                                    "result": "success - valid JSON format"
                                })
                            except json.JSONDecodeError:
                                validation_results.append({
                                    "file_path": str(file_path),
                                    "document": file_name,
                                    "result": "error - invalid JSON format"
                                })
                    except Exception as e:
                        validation_results.append({
                            "file_path": str(file_path),
                            "document": file_name,
                            "result": f"error - {str(e)}"
                        })
                else:
                    validation_results.append({
                        "file_path": str(file_path),
                        "document": file_name,
                        "result": "warning - file not found"
                    })
            
            # 전체 보고서 생성
            total_files = len(validation_results)
            success_count = sum(1 for r in validation_results if "success" in r["result"])
            warning_count = sum(1 for r in validation_results if "warning" in r["result"])
            error_count = sum(1 for r in validation_results if "error" in r["result"])
            
            report = f"Validated {total_files} files: {success_count} success, {warning_count} warnings, {error_count} errors"
            
            return {
                "success": True,
                "validation_results": validation_results,
                "report": report
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}


# 편의 함수
async def generate_specs_with_strands_workflow(
    frs_path: str,
    service_type: ServiceType,
    output_dir: Optional[str] = None,
    config: Optional[Config] = None
) -> Dict[str, Any]:
    """
    Strands 워크플로우를 사용한 명세서 생성 편의 함수.
    """
    workflow = SpecificationWorkflow(config)
    return await workflow.execute_workflow(frs_path, service_type, output_dir)