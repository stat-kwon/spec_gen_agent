"""
실용적인 Strands Agent SDK 기반 워크플로우
복잡한 state 관리 없이 필요한 기능만 포함
"""

import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import time
import json

from strands import Agent
from strands.models.openai import OpenAIModel

from .config import Config
from .models import ServiceType
from .tools import (
    load_frs_document,
    write_spec_file,
    create_git_branch,
    commit_changes,
    validate_markdown_structure,
    validate_openapi_spec
)
from .agents.spec_agents import (
    create_requirements_agent,
    create_design_agent,
    create_tasks_agent,
    create_changes_agent,
    create_openapi_agent,
    create_validation_agent
)


class SpecificationWorkflow:
    """
    실용적인 명세서 생성 워크플로우
    
    주요 기능:
    - Strands Agent SDK 기반 에이전트 실행
    - 간단한 상태 관리 (dict 사용)
    - 품질 평가 및 검증
    - Git 통합 (선택적)
    - 에러 핸들링 및 재시도
    """
    
    def __init__(self, config: Optional[Config] = None):
        """워크플로우 초기화"""
        self.config = config or Config.from_env()
        self.config.validate()
        
        # 간단한 상태 관리
        self.context = {
            'project': {},
            'documents': {},
            'quality': {},
            'metrics': {}
        }
        
        # 에이전트 컨테이너
        self.agents = {}
        
        # 저장된 파일 목록 추적
        self.saved_files = []
        
        # 세션 ID
        self.session_id = f"spec_gen_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        print(f"✅ 워크플로우 초기화 완료 (세션: {self.session_id})")
    
    def _initialize_agents(self):
        """에이전트 초기화"""
        print("🤖 에이전트 초기화 중...")
        
        self.agents = {
            'requirements': create_requirements_agent(self.config),
            'design': create_design_agent(self.config),
            'tasks': create_tasks_agent(self.config),
            'changes': create_changes_agent(self.config),
            'openapi': create_openapi_agent(self.config),
            'validation': create_validation_agent(self.config)
        }
        
        print(f"✅ {len(self.agents)}개 에이전트 초기화 완료")
    
    async def execute_workflow(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str] = None,
        use_git: bool = True
    ) -> Dict[str, Any]:
        """워크플로우 실행"""
        
        start_time = time.time()
        
        try:
            # 1. FRS 로드 및 프로젝트 정보 설정
            print(f"\n📖 FRS 로드 중: {frs_path}")
            await self._initialize_project(frs_path, service_type, output_dir)
            
            # 2. Git 브랜치 생성 (선택적)
            if use_git:
                await self._setup_git_branch()
            
            # 3. 에이전트 초기화
            self._initialize_agents()
            
            # 4. 에이전트 시퀀스 실행
            agent_sequence = self._get_agent_sequence(service_type)
            
            for agent_name in agent_sequence:
                print(f"\n🔄 {agent_name} 에이전트 실행 중...")
                agent_start = time.time()
                
                result = await self._execute_agent(agent_name)
                
                if result:
                    self.context['documents'][agent_name] = result
                    agent_time = time.time() - agent_start
                    print(f"✅ {agent_name} 완료 ({agent_time:.1f}초)")
                    
                    # 즉시 파일 저장
                    save_result = await self._save_agent_document(agent_name, result)
                    if save_result:
                        print(f"  📁 {save_result['filename']} 저장 완료 ({save_result['size']} bytes)")
                        print(f"     💾 위치: {save_result['file_path']}")
                    else:
                        print(f"  ⚠️ {agent_name} 문서 저장 실패 - 워크플로우는 계속 진행됩니다")
                else:
                    print(f"⚠️ {agent_name} 실행 실패")
            
            # 5. 품질 평가
            print("\n📊 품질 평가 실행 중...")
            quality_results = await self._evaluate_quality()
            
            # 6. 일관성 검증
            print("🔍 일관성 검증 실행 중...")
            consistency_results = await self._check_consistency()
            
            # 7. 문서 저장 (이미 저장된 파일 목록 수집)
            print("\n💾 저장된 파일 목록 수집 중...")
            files_written = await self._collect_saved_files()
            
            # 8. Git 커밋 (선택적)
            if use_git and files_written:
                await self._commit_changes(files_written)
            
            # 9. 결과 반환
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "session_id": self.session_id,
                "output_dir": self.context['project']['output_dir'],
                "files_written": files_written,
                "quality_results": quality_results,
                "consistency_results": consistency_results,
                "execution_time": execution_time,
                "framework": "Strands Agent SDK"
            }
            
        except Exception as e:
            error_msg = f"워크플로우 실행 실패: {str(e)}"
            print(f"❌ {error_msg}")
            
            # 부분적으로라도 저장된 파일이 있다면 반환
            partial_files = self.saved_files if hasattr(self, 'saved_files') else []
            
            return {
                "success": False,
                "session_id": self.session_id,
                "error": error_msg,
                "execution_time": time.time() - start_time,
                "files_written": partial_files,  # 부분 성공한 파일들
                "partial_success": len(partial_files) > 0
            }
    
    async def _initialize_project(
        self, 
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str]
    ):
        """프로젝트 정보 초기화"""
        # FRS 로드
        frs_result = load_frs_document(frs_path)
        if not frs_result.get("success"):
            raise ValueError(f"FRS 로드 실패: {frs_path}")
        
        # FRS ID 추출
        frs_id = self._extract_frs_id(frs_path)
        
        # 프로젝트 정보 설정
        self.context['project'] = {
            'frs_path': frs_path,
            'frs_id': frs_id,
            'frs_content': frs_result.get("content", ""),
            'service_type': service_type.value,
            'output_dir': output_dir or f"specs/{frs_id}/{service_type.value}"
        }
        
        # 출력 디렉토리 생성
        output_path = Path(self.context['project']['output_dir'])
        output_path.mkdir(parents=True, exist_ok=True)
        print(f"📁 출력 디렉토리: {self.context['project']['output_dir']}")
    
    async def _setup_git_branch(self):
        """Git 브랜치 설정"""
        frs_id = self.context['project']['frs_id']
        service_type = self.context['project']['service_type']
        
        git_result = create_git_branch(frs_id, service_type)
        if git_result.get("success"):
            print(f"🌿 Git 브랜치: {git_result.get('branch_name')}")
        else:
            print(f"⚠️ Git 브랜치 생성 실패: {git_result.get('error')}")
    
    def _get_agent_sequence(self, service_type: ServiceType) -> List[str]:
        """서비스 타입에 따른 에이전트 시퀀스 반환"""
        sequence = ['requirements', 'design', 'tasks', 'changes']
        
        if service_type == ServiceType.API:
            sequence.append('openapi')
        
        return sequence
    
    async def _execute_agent(self, agent_name: str) -> Optional[str]:
        """개별 에이전트 실행"""
        try:
            agent = self.agents.get(agent_name)
            if not agent:
                print(f"❌ 에이전트를 찾을 수 없음: {agent_name}")
                return None
            
            # 프롬프트 생성
            prompt = self._build_prompt(agent_name)
            
            # 에이전트 실행
            result = agent(prompt)
            
            # 결과 처리
            return self._process_agent_result(agent_name, result)
            
        except Exception as e:
            print(f"❌ {agent_name} 에이전트 실행 오류: {str(e)}")
            return None
    
    def _build_prompt(self, agent_name: str) -> str:
        """에이전트별 프롬프트 생성"""
        project = self.context['project']
        documents = self.context['documents']
        
        if agent_name == 'requirements':
            return f"""다음 FRS 문서를 분석하여 상세한 requirements.md를 생성하세요:

FRS 내용:
{project.get('frs_content', '')[:4000]}

서비스 유형: {project.get('service_type')}

요구사항:
1. 구조화된 requirements.md 형식으로 작성
2. 명확한 요구사항 ID 체계 사용 (REQ-001, REQ-002 등)
3. 기능/비기능/기술 요구사항 분리
4. 수용 기준 포함
5. 한국어로 작성"""

        elif agent_name == 'design':
            req_content = documents.get('requirements', '')[:3000]
            return f"""다음 요구사항을 바탕으로 상세한 design.md를 생성하세요:

요구사항:
{req_content}

서비스 유형: {project.get('service_type')}

요구사항:
1. 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함 (```mermaid 블록)
3. 데이터 모델 정의
4. API 계약 설계
5. 보안 및 성능 고려사항
6. 한국어로 작성"""

        elif agent_name == 'tasks':
            design_content = documents.get('design', '')[:3000]
            return f"""다음 설계를 바탕으로 상세한 tasks.md를 생성하세요:

설계:
{design_content}

요구사항:
1. Epic/Story/Task 계층 구조
2. 각 작업에 대한 명확한 설명
3. 예상 시간 및 우선순위
4. DoD (Definition of Done) 체크리스트
5. 의존성 표시
6. 한국어로 작성"""

        elif agent_name == 'changes':
            return f"""프로젝트 배포를 위한 상세한 changes.md를 생성하세요:

프로젝트: {project.get('frs_id')}
서비스 유형: {project.get('service_type')}

요구사항:
1. 버전 이력
2. 변경 사항 요약
3. 영향도 및 위험 분석
4. 롤백 계획
5. 알려진 이슈
6. 한국어로 작성"""

        elif agent_name == 'openapi':
            req_content = documents.get('requirements', '')[:2000]
            design_content = documents.get('design', '')[:2000]
            
            return f"""OpenAPI 3.1 명세를 JSON 형식으로 생성하세요:

요구사항:
{req_content}

설계:
{design_content}

요구사항:
1. 유효한 JSON 형식 (마크다운 블록 없이)
2. OpenAPI 3.1 스펙 준수
3. 5-10개의 핵심 엔드포인트
4. 요청/응답 스키마 포함
5. 인증 및 오류 처리
6. JSON만 출력 (설명 없음)"""

        return "작업을 수행하세요."
    
    def _process_agent_result(self, agent_name: str, result: Any) -> str:
        """에이전트 결과 처리"""
        result_str = str(result)
        
        # OpenAPI JSON인 경우 마크다운 블록 제거
        if agent_name == 'openapi':
            # ```json 블록 제거
            if result_str.startswith('```json'):
                result_str = result_str[7:]
            if result_str.startswith('```'):
                result_str = result_str[3:]
            if result_str.endswith('```'):
                result_str = result_str[:-3]
            result_str = result_str.strip()
        
        return result_str
    
    async def _save_agent_document(self, agent_name: str, content: str) -> Optional[Dict[str, Any]]:
        """개별 에이전트 문서 즉시 저장"""
        try:
            output_dir = self.context['project']['output_dir']
            
            # 파일명 결정
            if agent_name == 'openapi':
                filename = 'apis.json'
            else:
                filename = f'{agent_name}.md'
            
            # 파일 저장
            result = await write_spec_file(output_dir, content, filename)
            
            if result.get("success"):
                file_info = {
                    "filename": filename,
                    "file_path": result.get("file_path"),
                    "size": result.get("size", 0)
                }
                # 저장된 파일 목록에 추가
                self.saved_files.append(result.get("file_path"))
                return file_info
            else:
                print(f"  ❌ {filename} 저장 실패: {result.get('error')}")
                return None
                
        except Exception as e:
            print(f"  ❌ {agent_name} 문서 저장 중 오류: {str(e)}")
            return None
    
    async def _evaluate_quality(self) -> Dict[str, Dict[str, float]]:
        """문서 품질 평가"""
        quality_results = {}
        
        for doc_type, content in self.context['documents'].items():
            if not content:
                continue
            
            # 기본 품질 점수
            score = {
                'completeness': 100.0,
                'structure': 100.0,
                'clarity': 100.0,
                'overall': 100.0
            }
            
            # 길이 체크
            if len(content) < 500:
                score['completeness'] -= 30
            elif len(content) < 1000:
                score['completeness'] -= 15
            
            # 구조 체크
            if doc_type == 'requirements' and 'REQ-' not in content:
                score['structure'] -= 20
            if doc_type == 'design' and '```mermaid' not in content:
                score['structure'] -= 20
            if doc_type == 'tasks' and 'Epic' not in content:
                score['structure'] -= 20
            
            # 전체 점수 계산
            score['overall'] = (
                score['completeness'] * 0.4 +
                score['structure'] * 0.4 +
                score['clarity'] * 0.2
            )
            
            quality_results[doc_type] = score
            
            # 품질 경고
            if score['overall'] < 70:
                print(f"⚠️ {doc_type} 품질 낮음: {score['overall']:.1f}점")
        
        return quality_results
    
    async def _check_consistency(self) -> Dict[str, List[str]]:
        """문서 간 일관성 검증"""
        issues = []
        
        documents = self.context['documents']
        
        # 요구사항-설계 일관성
        if 'requirements' in documents and 'design' in documents:
            req_ids = self._extract_requirement_ids(documents['requirements'])
            if req_ids and not any(rid in documents['design'] for rid in req_ids):
                issues.append("설계 문서에서 요구사항 ID 참조 없음")
        
        # 설계-작업 일관성
        if 'design' in documents and 'tasks' in documents:
            if 'API' in documents['design'] and 'API' not in documents['tasks']:
                issues.append("설계에 API가 있지만 작업에는 없음")
        
        return {"consistency_issues": issues}
    
    def _extract_requirement_ids(self, content: str) -> List[str]:
        """요구사항 ID 추출"""
        import re
        pattern = r'REQ-\d{3}'
        return re.findall(pattern, content)
    
    async def _collect_saved_files(self) -> List[str]:
        """저장된 파일 목록 수집"""
        print(f"  📁 총 {len(self.saved_files)}개 파일이 저장됨")
        for file_path in self.saved_files:
            filename = Path(file_path).name
            print(f"    ✅ {filename}")
        return self.saved_files
    
    async def _commit_changes(self, files_written: List[str]):
        """Git 커밋"""
        frs_id = self.context['project']['frs_id']
        service_type = self.context['project']['service_type']
        
        result = commit_changes(frs_id, service_type, files_written)
        
        if result.get("success"):
            print(f"✅ Git 커밋 완료: {result.get('commit_hash', '')[:8]}")
        else:
            print(f"⚠️ Git 커밋 실패: {result.get('error')}")
    
    def _extract_frs_id(self, frs_path: str) -> str:
        """FRS ID 추출"""
        import re
        match = re.search(r'FRS-(\d+)', frs_path)
        if match:
            return f"FRS-{match.group(1)}"
        return Path(frs_path).stem
    
    def validate_existing_specs(self, spec_dir: str) -> Dict[str, Any]:
        """기존 명세서 검증"""
        try:
            spec_path = Path(spec_dir)
            
            if not spec_path.exists() or not spec_path.is_dir():
                return {"success": False, "error": f"디렉토리를 찾을 수 없음: {spec_dir}"}
            
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
                    # 파일 검증
                    if file_name.endswith('.md'):
                        result = validate_markdown_structure(str(file_path))
                    elif file_name.endswith('.json'):
                        result = validate_openapi_spec(str(file_path))
                    else:
                        result = {"success": True}
                    
                    validation_results.append({
                        "file": file_name,
                        "exists": True,
                        "valid": result.get("success", False),
                        "error": result.get("error")
                    })
                else:
                    validation_results.append({
                        "file": file_name,
                        "exists": False,
                        "valid": False,
                        "error": "파일이 존재하지 않음"
                    })
            
            # 전체 결과 계산
            total_files = len(validation_results)
            valid_files = sum(1 for r in validation_results if r["valid"])
            
            return {
                "success": True,
                "validation_results": validation_results,
                "summary": {
                    "total_files": total_files,
                    "valid_files": valid_files,
                    "invalid_files": total_files - valid_files
                }
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}