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
from strands.multiagent import GraphBuilder
from strands.session.file_session_manager import FileSessionManager

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
    create_validation_agent,
    create_quality_assessor_agent,
    create_consistency_checker_agent,
    create_coordinator_agent,
    # Simple 버전들
    create_tasks_agent,
    create_changes_agent_simple,
    create_openapi_agent_simple
)
from .models.quality import (
    QualityReport,
    ConsistencyReport,
    ApprovalDecision,
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
        
        # 세션 매니저 설정
        self.session_manager = FileSessionManager(
            session_id=self.session_id,
            base_dir="./sessions"
        )
        
        # 기본 문서 생성 에이전트들 (Simple 버전 사용)
        self.agents = {
            'requirements': create_requirements_agent(self.config),  # 이미 simple 버전
            'design': create_design_agent(self.config),  # 이미 simple 버전
            'tasks': create_tasks_agent(self.config),
            'changes': create_changes_agent_simple(self.config),
            'openapi': create_openapi_agent_simple(self.config),
            'validation': create_validation_agent(self.config),
            # 품질 평가 에이전트들
            'quality_assessor': create_quality_assessor_agent(self.config),
            'consistency_checker': create_consistency_checker_agent(self.config),
            'coordinator': create_coordinator_agent(self.config)
        }
        
        # 모든 에이전트에 세션 매니저 연결
        for agent in self.agents.values():
            agent.session_manager = self.session_manager
        
        print(f"✅ {len(self.agents)}개 에이전트 초기화 완료 (세션 관리 포함)")
        
        # 파일 기반 컨텍스트를 위한 에이전트 래핑
        self._wrap_agents_with_file_context()
    
    def _wrap_agents_with_file_context(self):
        """에이전트들을 파일 기반 컨텍스트 로더로 래핑 (Strands Agent 객체 구조 유지)"""
        
        # 에이전트별 의존성 매핑 저장 (래핑 대신 별도 저장)
        self._agent_dependencies = {
            'requirements': [],  # FRS 내용만 필요
            'design': ['requirements'],
            'tasks': ['requirements', 'design'], 
            'changes': ['requirements', 'design', 'tasks'],
            'openapi': ['requirements', 'design', 'tasks'],
            'quality_assessor': ['requirements', 'design', 'tasks', 'changes', 'openapi'],
            'consistency_checker': ['requirements', 'design', 'tasks', 'changes', 'openapi'],
            'coordinator': ['requirements', 'design', 'tasks', 'changes', 'openapi']
        }
        
        print(f"  ✅ 파일 기반 컨텍스트 의존성 설정 완료")
    
    def _inject_file_contexts_to_agents(self):
        """실행 시점에 각 에이전트에 필요한 파일 컨텍스트를 동적으로 주입"""
        try:
            print("📝 에이전트별 파일 컨텍스트 주입 중...")
            
            # 컨텍스트 주입이 필요한 에이전트들만 처리
            context_agents = ['design', 'tasks', 'changes', 'openapi', 'quality_assessor', 'consistency_checker', 'coordinator']
            
            for agent_name in context_agents:
                if agent_name in self.agents:
                    agent = self.agents[agent_name]
                    
                    # 에이전트별 필요 파일 컨텍스트 로드
                    needed_files = self._agent_dependencies.get(agent_name, [])
                    
                    if needed_files:
                        file_context = self._load_context_from_files(needed_files)
                        
                        if file_context:
                            # 에이전트의 system prompt에 파일 컨텍스트 추가
                            if hasattr(agent, 'prompt_template') and agent.prompt_template:
                                original_prompt = agent.prompt_template
                                enhanced_prompt = f"{original_prompt}\n\n## 참조 문서\n{file_context}"
                                agent.prompt_template = enhanced_prompt
                                print(f"  ✅ {agent_name} 컨텍스트 주입 완료")
                            else:
                                print(f"  ⚠️ {agent_name} prompt_template 속성 없음")
                        else:
                            print(f"  ℹ️ {agent_name} 로드할 파일 컨텍스트 없음")
                    else:
                        print(f"  ℹ️ {agent_name} 파일 의존성 없음")
                        
        except Exception as e:
            print(f"  ❌ 파일 컨텍스트 주입 실패: {str(e)}")
            import traceback
            traceback.print_exc()
    
    async def execute_workflow(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str] = None,
        use_git: bool = True
    ) -> Dict[str, Any]:
        """Graph 기반 워크플로우 실행"""
        
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
            
            # 4. Graph 기반 워크플로우 실행
            print("\n🔄 Graph 기반 워크플로우 시작...")
            graph_result = await self._execute_graph_workflow(service_type)
            
            # 5. 문서 저장 (이미 저장된 파일 목록 수집)
            print("\n💾 저장된 파일 목록 수집 중...")
            files_written = await self._collect_saved_files()
            
            # 6. Git 커밋 (선택적)
            if use_git and files_written:
                await self._commit_changes(files_written)
            
            # 7. 결과 반환
            execution_time = time.time() - start_time
            
            return {
                "success": True,
                "session_id": self.session_id,
                "output_dir": self.context['project']['output_dir'],
                "files_written": files_written,
                "graph_result": graph_result,
                "execution_time": execution_time,
                "framework": "Strands Agent SDK - Graph"
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
    
    async def _execute_graph_workflow(self, service_type: ServiceType) -> Dict[str, Any]:
        """Agentic AI Graph - 품질 평가 및 피드백 루프 포함"""
        
        print("🚀 Agentic AI Graph 시작 (품질 평가 + 피드백 루프)...")
        
        try:
            # GraphBuilder 초기화
            builder = GraphBuilder()
            
            # 1. 문서 생성 에이전트 노드 추가
            builder.add_node(self.agents['requirements'], 'requirements')
            builder.add_node(self.agents['design'], 'design')
            builder.add_node(self.agents['tasks'], 'tasks')
            builder.add_node(self.agents['changes'], 'changes')
            builder.add_node(self.agents['openapi'], 'openapi')
            
            # 2. 품질 평가 에이전트 노드 추가
            builder.add_node(self.agents['quality_assessor'], 'quality_assessor')
            builder.add_node(self.agents['consistency_checker'], 'consistency_checker')
            builder.add_node(self.agents['coordinator'], 'coordinator')
            
            # 3. 기본 순차 실행 엣지
            builder.add_edge('requirements', 'design')
            builder.add_edge('design', 'tasks') 
            builder.add_edge('tasks', 'changes')
            builder.add_edge('changes', 'openapi')
            
            # 4. 품질 평가 엣지 (openapi 완료 후)
            builder.add_edge('openapi', 'quality_assessor')
            builder.add_edge('quality_assessor', 'consistency_checker')
            builder.add_edge('consistency_checker', 'coordinator')
            
            # 5. 피드백 루프 (coordinator가 개선 필요 판단 시)
            builder.add_edge('coordinator', 'requirements', condition=self._needs_improvement)
            
            # 6. Design이 Requirements에 피드백 제공
            builder.add_edge('design', 'requirements', condition=self._design_has_feedback)
            
            # 7. 개별 파일 타겟팅 피드백 엣지들
            builder.add_edge('coordinator', 'requirements', condition=self._needs_req_improvement)
            builder.add_edge('coordinator', 'design', condition=self._needs_design_improvement)
            builder.add_edge('coordinator', 'tasks', condition=self._needs_tasks_improvement)
            builder.add_edge('coordinator', 'changes', condition=self._needs_changes_improvement)
            builder.add_edge('coordinator', 'openapi', condition=self._needs_openapi_improvement)
            
            # 8. 종속성 관리 - 특정 파일 수정 시 하위 파일들도 연쇄 업데이트
            # (현재는 기본 순차 엣지가 이 역할을 담당하므로 추가 엣지는 불필요)
            
            # Graph 설정
            builder.set_entry_point('requirements')
            builder.set_max_node_executions(30)  # 피드백 루프를 위한 충분한 실행 횟수
            
            # Graph 빌드
            graph = builder.build()
            
            # 초기 프롬프트 (FRS 내용)
            frs_content = self.context['project']['frs_content']
            initial_prompt = f"FRS 내용: {frs_content}\n\n제공된 FRS를 기반으로 상세한 기술 요구사항 문서를 생성하세요."
            
            print("🔄 Graph 실행 중 (파일 기반 컨텍스트 자동 주입)...")
            
            # 각 에이전트의 system prompt에 파일 컨텍스트 사전 주입
            self._inject_file_contexts_to_agents()
            
            # Graph 실행 - Strands가 자동으로 컨텍스트 전파
            result = graph(initial_prompt)
            
            print("✅ Graph 실행 완료")
            print(f"결과: {str(result)[:200]}...")
            
            # Graph 결과 디버깅
            if hasattr(result, 'results'):
                print(f"🔍 Graph 노드 결과: {list(result.results.keys())}")
                for node_name in result.results.keys():
                    node_result = result.results[node_name]
                    print(f"  - {node_name}: 실행됨")
                    if hasattr(node_result, 'result'):
                        print(f"    출력 길이: {len(str(node_result.result))}")
                
                print(f"🔍 예상 노드: ['requirements', 'design', 'tasks', 'changes', 'openapi']")
                missing_nodes = set(['requirements', 'design', 'tasks', 'changes', 'openapi']) - set(result.results.keys())
                if missing_nodes:
                    print(f"❌ 실행되지 않은 노드: {missing_nodes}")
            
            # Graph 결과에서 파일 저장
            saved_files = await self._save_graph_results_simple(result)
            
            return {
                'success': True,
                'result': result,
                'saved_files': saved_files,
                'execution_type': 'simple_graph'
            }
            
        except Exception as e:
            print(f"❌ Simple Graph 실패: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def _needs_improvement(self, state) -> bool:
        """Coordinator가 전체 문서 개선이 필요하다고 판단하는지 확인"""
        try:
            coordinator_output = str(state)
            
            # 개선 필요 키워드 체크
            improvement_needed = any(keyword in coordinator_output for keyword in [
                "개선", "미흡", "부족", "불충분", "required_improvements", "거부", "rejected"
            ])
            
            # 개선 횟수 추적
            if not hasattr(self, '_improvement_count'):
                self._improvement_count = 0
            
            if improvement_needed and self._improvement_count < 3:  # 최대 3회 개선
                self._improvement_count += 1
                print(f"🔄 Coordinator가 문서 개선 요청 ({self._improvement_count}/3)")
                self._coordinator_feedback = coordinator_output
                return True
            
            if self._improvement_count >= 3:
                print("✅ 최대 개선 횟수 도달 - 문서 완성")
            else:
                print("✅ Coordinator 승인 - 품질 기준 충족")
            return False
            
        except Exception as e:
            print(f"⚠️ 개선 판정 오류: {str(e)}")
            return False
    
    def _design_has_feedback(self, state) -> bool:
        """Design 에이전트가 requirements에 피드백을 제공하는지 확인"""
        try:
            design_output = str(state)
            
            # 피드백 키워드 체크
            has_feedback = any(keyword in design_output for keyword in [
                "추가", "보완", "구체화", "명확", "GDPR", "보안"
            ])
            
            # 피드백 횟수 제한
            if not hasattr(self, '_design_feedback_count'):
                self._design_feedback_count = 0
            
            if has_feedback and self._design_feedback_count < 1:  # 1회만
                self._design_feedback_count += 1
                print("💬 Design이 Requirements에 피드백 제공")
                self._design_feedback = design_output
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ 피드백 판정 오류: {str(e)}")
            return False
    
    # === 개별 파일 타겟팅 피드백 함수들 ===
    
    def _needs_req_improvement(self, state) -> bool:
        """Requirements 문서만 개선이 필요한지 판단"""
        try:
            coordinator_output = str(state)
            
            # Requirements 관련 개선 키워드 체크
            req_keywords = [
                "requirements", "요구사항", "REQ-", "기능 요구사항", "요구 사항"
            ]
            
            improvement_keywords = [
                "개선", "미흡", "부족", "불충분", "required_improvements"
            ]
            
            # 개선 필요 + Requirements 관련 키워드 동시 존재 확인
            has_improvement = any(keyword in coordinator_output for keyword in improvement_keywords)
            has_req_mention = any(keyword in coordinator_output for keyword in req_keywords)
            
            if has_improvement and has_req_mention:
                if not hasattr(self, '_req_improvement_count'):
                    self._req_improvement_count = 0
                
                if self._req_improvement_count < 2:  # Requirements는 최대 2회 개선
                    self._req_improvement_count += 1
                    print(f"🎯 Requirements 파일 개별 개선 요청 ({self._req_improvement_count}/2)")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"⚠️ Requirements 개선 판단 오류: {str(e)}")
            return False
    
    def _needs_design_improvement(self, state) -> bool:
        """Design 문서만 개선이 필요한지 판단"""
        try:
            coordinator_output = str(state)
            
            # Design 관련 개선 키워드 체크
            design_keywords = [
                "design", "설계", "아키텍처", "기술 스택", "검토 의견"
            ]
            
            improvement_keywords = [
                "개선", "미흡", "부족", "불충분", "required_improvements"
            ]
            
            has_improvement = any(keyword in coordinator_output for keyword in improvement_keywords)
            has_design_mention = any(keyword in coordinator_output for keyword in design_keywords)
            
            if has_improvement and has_design_mention:
                if not hasattr(self, '_design_improvement_count'):
                    self._design_improvement_count = 0
                
                if self._design_improvement_count < 2:
                    self._design_improvement_count += 1
                    print(f"🎯 Design 파일 개별 개선 요청 ({self._design_improvement_count}/2)")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"⚠️ Design 개선 판단 오류: {str(e)}")
            return False
    
    def _needs_tasks_improvement(self, state) -> bool:
        """Tasks 문서만 개선이 필요한지 판단"""
        try:
            coordinator_output = str(state)
            
            # Tasks 관련 개선 키워드 체크
            tasks_keywords = [
                "tasks", "작업", "TASK-", "작업 분해", "업무"
            ]
            
            improvement_keywords = [
                "개선", "미흡", "부족", "불충분", "required_improvements"
            ]
            
            has_improvement = any(keyword in coordinator_output for keyword in improvement_keywords)
            has_tasks_mention = any(keyword in coordinator_output for keyword in tasks_keywords)
            
            if has_improvement and has_tasks_mention:
                if not hasattr(self, '_tasks_improvement_count'):
                    self._tasks_improvement_count = 0
                
                if self._tasks_improvement_count < 2:
                    self._tasks_improvement_count += 1
                    print(f"🎯 Tasks 파일 개별 개선 요청 ({self._tasks_improvement_count}/2)")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"⚠️ Tasks 개선 판단 오류: {str(e)}")
            return False
    
    def _needs_changes_improvement(self, state) -> bool:
        """Changes 문서만 개선이 필요한지 판단"""
        try:
            coordinator_output = str(state)
            
            # Changes 관련 개선 키워드 체크
            changes_keywords = [
                "changes", "변경", "핵심 요구사항", "변경 요약", "배포"
            ]
            
            improvement_keywords = [
                "개선", "미흡", "부족", "불충분", "required_improvements"
            ]
            
            has_improvement = any(keyword in coordinator_output for keyword in improvement_keywords)
            has_changes_mention = any(keyword in coordinator_output for keyword in changes_keywords)
            
            if has_improvement and has_changes_mention:
                if not hasattr(self, '_changes_improvement_count'):
                    self._changes_improvement_count = 0
                
                if self._changes_improvement_count < 2:
                    self._changes_improvement_count += 1
                    print(f"🎯 Changes 파일 개별 개선 요청 ({self._changes_improvement_count}/2)")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"⚠️ Changes 개선 판단 오류: {str(e)}")
            return False
    
    def _needs_openapi_improvement(self, state) -> bool:
        """OpenAPI 문서만 개선이 필요한지 판단"""
        try:
            coordinator_output = str(state)
            
            # OpenAPI 관련 개선 키워드 체크
            api_keywords = [
                "api", "openapi", "엔드포인트", "endpoint", "API 엔드포인트"
            ]
            
            improvement_keywords = [
                "개선", "미흡", "부족", "불충분", "required_improvements"
            ]
            
            has_improvement = any(keyword in coordinator_output for keyword in improvement_keywords)
            has_api_mention = any(keyword in coordinator_output for keyword in api_keywords)
            
            if has_improvement and has_api_mention:
                if not hasattr(self, '_api_improvement_count'):
                    self._api_improvement_count = 0
                
                if self._api_improvement_count < 2:
                    self._api_improvement_count += 1
                    print(f"🎯 OpenAPI 파일 개별 개선 요청 ({self._api_improvement_count}/2)")
                    return True
                    
            return False
            
        except Exception as e:
            print(f"⚠️ OpenAPI 개선 판단 오류: {str(e)}")
            return False
    
    def _build_requirements_prompt_with_feedback(self, frs_content: str) -> str:
        """피드백을 반영한 Requirements 프롬프트 생성"""
        base_prompt = f"FRS 내용: {frs_content}\n\n제공된 FRS를 기반으로 상세한 기술 요구사항 문서를 생성하세요."
        
        # 저장된 피드백이 있으면 추가
        if hasattr(self, '_stored_feedback') and self._stored_feedback:
            feedback_prompt = f"\n\n**피드백 반영 필요:**\n{self._stored_feedback}\n\n위 피드백을 반영하여 요구사항을 개선해주세요."
            return base_prompt + feedback_prompt
        
        return base_prompt
    
    async def _save_graph_results_simple(self, graph_result) -> List[str]:
        """Simple Graph 결과를 파일로 저장"""
        saved_files = []
        
        try:
            print("💾 Graph 결과 파일 저장 중...")
            
            # Graph 결과에서 각 노드의 결과 추출
            if hasattr(graph_result, 'results') and graph_result.results:
                
                # Requirements 결과 저장
                if 'requirements' in graph_result.results:
                    req_result = graph_result.results['requirements']
                    if hasattr(req_result, 'result') and hasattr(req_result.result, 'message'):
                        content = req_result.result.message.get('content', [])
                        if content and isinstance(content, list) and len(content) > 0:
                            req_text = content[0].get('text', '')
                            if req_text:
                                save_result = self._save_agent_document_sync('requirements', req_text)
                                if save_result:
                                    saved_files.append(save_result['file_path'])
                                    print(f"  📁 {save_result['filename']} 저장 완료")
                
                # Design 결과 저장
                if 'design' in graph_result.results:
                    design_result = graph_result.results['design']
                    if hasattr(design_result, 'result') and hasattr(design_result.result, 'message'):
                        content = design_result.result.message.get('content', [])
                        if content and isinstance(content, list) and len(content) > 0:
                            design_text = content[0].get('text', '')
                            if design_text:
                                save_result = self._save_agent_document_sync('design', design_text)
                                if save_result:
                                    saved_files.append(save_result['file_path'])
                                    print(f"  📁 {save_result['filename']} 저장 완료")
                
                # Tasks 결과 저장
                if 'tasks' in graph_result.results:
                    tasks_result = graph_result.results['tasks']
                    if hasattr(tasks_result, 'result') and hasattr(tasks_result.result, 'message'):
                        content = tasks_result.result.message.get('content', [])
                        if content and isinstance(content, list) and len(content) > 0:
                            tasks_text = content[0].get('text', '')
                            if tasks_text:
                                save_result = self._save_agent_document_sync('tasks', tasks_text)
                                if save_result:
                                    saved_files.append(save_result['file_path'])
                                    print(f"  📁 {save_result['filename']} 저장 완료")
                
                # Changes 결과 저장
                if 'changes' in graph_result.results:
                    changes_result = graph_result.results['changes']
                    if hasattr(changes_result, 'result') and hasattr(changes_result.result, 'message'):
                        content = changes_result.result.message.get('content', [])
                        if content and isinstance(content, list) and len(content) > 0:
                            changes_text = content[0].get('text', '')
                            if changes_text:
                                save_result = self._save_agent_document_sync('changes', changes_text)
                                if save_result:
                                    saved_files.append(save_result['file_path'])
                                    print(f"  📁 {save_result['filename']} 저장 완료")
                
                # OpenAPI 결과 저장
                if 'openapi' in graph_result.results:
                    openapi_result = graph_result.results['openapi']
                    if hasattr(openapi_result, 'result') and hasattr(openapi_result.result, 'message'):
                        content = openapi_result.result.message.get('content', [])
                        if content and isinstance(content, list) and len(content) > 0:
                            openapi_text = content[0].get('text', '')
                            if openapi_text:
                                # OpenAPI는 JSON 파일로 저장 (service_type이 api인 경우)
                                if self.context['project']['service_type'] == 'api':
                                    save_result = self._save_agent_document_sync('openapi', openapi_text)
                                    if save_result:
                                        saved_files.append(save_result['file_path'])
                                        print(f"  📁 {save_result['filename']} 저장 완료")
            
            print(f"✅ {len(saved_files)}개 파일 저장 완료")
            return saved_files
            
        except Exception as e:
            print(f"❌ 파일 저장 실패: {str(e)}")
            return saved_files
    
    def _create_saving_agent_wrapper(self, agent_name: str):
        """파일 저장 기능이 포함된 에이전트 래퍼 생성"""
        from strands import Agent
        
        original_agent = self.agents[agent_name]
        
        class SavingAgentWrapper:
            """결과를 즉시 파일로 저장하는 에이전트 래퍼"""
            
            def __init__(self, original_agent, workflow, agent_name):
                self.original_agent = original_agent
                self.workflow = workflow
                self.agent_name = agent_name
                # Agent의 모든 속성을 래퍼에서도 접근 가능하게 함
                for attr in dir(original_agent):
                    if not attr.startswith('_') and not callable(getattr(original_agent, attr)):
                        setattr(self, attr, getattr(original_agent, attr))
            
            def __call__(self, prompt):
                """에이전트 실행 및 즉시 파일 저장"""
                print(f"🔄 {self.agent_name} 에이전트 실행 중...")
                
                # 원본 에이전트 실행
                result = self.original_agent(prompt)
                result_text = self.workflow._process_agent_result(self.agent_name, result)
                
                # 즉시 파일 저장 (동기 함수로 변경)
                try:
                    output_dir = self.workflow.context['project']['output_dir']
                    
                    # 파일명 결정
                    if self.agent_name == 'openapi':
                        filename = 'apis.json'
                    else:
                        filename = f'{self.agent_name}.md'
                    
                    # 파일 저장 (동기 버전 사용)
                    from pathlib import Path
                    file_path = Path(output_dir) / filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 기존 파일 존재 여부 확인
                    is_update = file_path.exists()
                    action = "업데이트" if is_update else "생성"
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(result_text)
                    file_size = file_path.stat().st_size
                    
                    print(f"  📁 {filename} {action} 완료 ({file_size} bytes)")
                    print(f"     💾 위치: {file_path}")
                    
                    # 저장된 파일 목록에 추가 (중복 방지)
                    file_path_str = str(file_path)
                    if file_path_str not in self.workflow.saved_files:
                        self.workflow.saved_files.append(file_path_str)
                
                except Exception as e:
                    print(f"  ❌ {self.agent_name} 파일 저장 실패: {str(e)}")
                
                print(f"✅ {self.agent_name} 완료")
                return result_text
            
            def __getattr__(self, name):
                """원본 에이전트의 속성에 접근"""
                return getattr(self.original_agent, name)
        
        return SavingAgentWrapper(original_agent, self, agent_name)
    
    def _need_revision(self, state) -> bool:
        """품질 평가 결과 기반 재작업 필요 여부 판단"""
        try:
            # Graph의 state에서 coordinator 출력 확인
            # Strands Graph는 마지막 노드의 출력을 직접 전달할 수 있음
            coordinator_output = state
            
            # coordinator가 JSON 형태로 결과를 반환한다고 가정
            if isinstance(coordinator_output, str):
                try:
                    decision_data = json.loads(coordinator_output)
                    approved = decision_data.get('approved', False)
                    
                    if not approved:
                        print(f"🔄 재작업 필요: {decision_data.get('reason', '품질 기준 미달')}")
                        return True
                    else:
                        print(f"✅ 최종 승인: {decision_data.get('reason', '품질 기준 충족')}")
                        return False
                        
                except json.JSONDecodeError:
                    print("⚠️ coordinator 결과 파싱 실패")
                    return False
            
            # 기본적으로 승인으로 간주
            print("✅ 기본 승인 (결과 파싱 불가)")
            return False
                
        except Exception as e:
            print(f"⚠️ 재작업 판정 중 오류: {str(e)}")
            return False
    
    async def _execute_fallback_workflow(self, service_type: ServiceType) -> Dict[str, Any]:
        """Graph 실행 실패시 fallback 워크플로우"""
        print("🔄 Fallback 워크플로우로 전환...")
        
        # 기본 문서 생성 순서
        agent_sequence = ['requirements', 'design', 'tasks', 'changes']
        if service_type == ServiceType.API:
            agent_sequence.append('openapi')
        
        # 품질 평가 에이전트들
        quality_agents = ['quality_assessor', 'consistency_checker', 'coordinator']
        
        # 최대 3회 시도
        for iteration in range(1, 4):
            print(f"\n🔄 시도 {iteration}/3")
            
            # 1. 기본 문서 생성
            documents = {}
            for agent_name in agent_sequence:
                print(f"🔄 {agent_name} 에이전트 실행 중...")
                result = await self._execute_agent(agent_name, {'iteration': iteration})
                if result:
                    documents[agent_name] = result
                    print(f"✅ {agent_name} 완료")
                else:
                    print(f"❌ {agent_name} 실패")
            
            # 2. 품질 평가
            print("\n📊 품질 평가 단계...")
            quality_results = {}
            
            for agent_name in quality_agents:
                print(f"🔄 {agent_name} 실행 중...")
                # 이전 문서들을 상태로 전달
                state = {'results': documents, 'iteration': iteration}
                result = await self._execute_agent(agent_name, state)
                if result:
                    quality_results[agent_name] = result
                    print(f"✅ {agent_name} 완료")
            
            # 3. 승인 여부 확인
            coordinator_result = quality_results.get('coordinator')
            if coordinator_result:
                try:
                    decision_data = json.loads(coordinator_result)
                    if decision_data.get('approved', False):
                        print(f"🎉 {iteration}회차에서 승인 완료!")
                        return {
                            'success': True,
                            'iteration': iteration,
                            'documents': documents,
                            'quality_results': quality_results
                        }
                    else:
                        print(f"🔄 {iteration}회차 거부: {decision_data.get('reason', '품질 기준 미달')}")
                        if iteration < 3:
                            print("📝 피드백을 반영하여 재시도...")
                            # 다음 iteration에서 피드백 활용
                except Exception as e:
                    print(f"⚠️ 승인 결과 파싱 실패: {str(e)}")
        
        print("❌ 3회 시도 후에도 품질 기준 미달")
        return {
            'success': False,
            'final_iteration': 3,
            'reason': '최대 시도 횟수 초과'
        }
    
    async def _execute_agent(self, agent_name: str, state: Dict[str, Any] = None) -> Optional[str]:
        """개별 에이전트 실행 (async 버전)"""
        try:
            agent = self.agents.get(agent_name)
            if not agent:
                print(f"❌ 에이전트를 찾을 수 없음: {agent_name}")
                return None
            
            # 프롬프트 생성 (상태 기반)
            prompt = self._build_prompt_from_state(agent_name, state or {})
            
            # 품질 평가 에이전트들은 structured output 사용
            if agent_name in ['quality_assessor', 'consistency_checker', 'coordinator']:
                result = await self._execute_structured_agent(agent_name, agent, prompt)
            else:
                # 일반 에이전트는 동기 호출 (ainvoke 메서드가 없음)
                result = agent(prompt)
                result_text = self._process_agent_result(agent_name, result)
                
                # 즉시 파일 저장
                if result_text:
                    save_result = await self._save_agent_document(agent_name, result_text)
                    if save_result:
                        print(f"  📁 {save_result['filename']} 저장 완료")
                
                result = result_text
            
            return result
            
        except Exception as e:
            print(f"❌ {agent_name} 에이전트 실행 오류: {str(e)}")
            return None
    
    async def _execute_structured_agent(self, agent_name: str, agent: Agent, prompt: str) -> str:
        """Structured Output을 사용하는 에이전트 실행"""
        try:
            if agent_name == 'quality_assessor':
                result = agent.structured_output(QualityReport, prompt)
                result_json = result.model_dump_json()
                print(f"  📊 품질 평가: 전체 {result.overall}점")
                return result_json
                
            elif agent_name == 'consistency_checker':
                result = agent.structured_output(ConsistencyReport, prompt)
                result_json = result.model_dump_json()
                print(f"  🔍 일관성 검증: {len(result.issues)}개 이슈 발견 ({result.severity})")
                return result_json
                
            elif agent_name == 'coordinator':
                result = agent.structured_output(ApprovalDecision, prompt)
                result_json = result.model_dump_json()
                status = "승인" if result.approved else "거부"
                print(f"  🎯 최종 결정: {status} (신뢰도: {result.confidence}%)")
                return result_json
                
        except Exception as e:
            print(f"  ❌ {agent_name} structured output 실행 실패: {str(e)}")
            # fallback: 일반 호출
            result = agent(prompt)
            return self._extract_agent_result(result)
    
    def _extract_agent_result(self, result) -> str:
        """에이전트 결과에서 텍스트 추출"""
        if hasattr(result, 'content'):
            return str(result.content)
        elif hasattr(result, 'message'):
            return str(result.message.get('content', ''))
        else:
            return str(result)
    
    def _build_prompt_from_state(self, agent_name: str, state: Dict[str, Any]) -> str:
        """상태 기반 에이전트별 프롬프트 생성"""
        # 상태에서 기본 정보 추출
        frs_content = state.get('frs_content', self.context['project'].get('frs_content', ''))
        service_type = state.get('service_type', self.context['project'].get('service_type', ''))
        
        # 이전 결과들 추출 (Graph 상태에서)
        results = state.get('results', {})
        
        if agent_name == 'requirements':
            return self._build_requirements_prompt(frs_content, service_type, results)
        elif agent_name == 'design':
            return self._build_design_prompt(results.get('requirements', {}), service_type)
        elif agent_name == 'tasks':
            return self._build_tasks_prompt(results.get('design', {}))
        elif agent_name == 'changes':
            return self._build_changes_prompt(service_type)
        elif agent_name == 'openapi':
            return self._build_openapi_prompt(results.get('requirements', {}), results.get('design', {}))
        elif agent_name == 'quality_assessor':
            return self._build_quality_prompt(results)
        elif agent_name == 'consistency_checker':
            return self._build_consistency_prompt(results)
        elif agent_name == 'coordinator':
            return self._build_coordinator_prompt(results)
        
        return "작업을 수행하세요."
    
    def _build_requirements_prompt(self, frs_content: str, service_type: str, results: Dict) -> str:
        """요구사항 에이전트 프롬프트"""
        # 재작업인 경우 이전 피드백 포함
        feedback_section = ""
        if 'coordinator' in results:
            try:
                coordinator_data = json.loads(results['coordinator'].get('content', '{}'))
                improvements = coordinator_data.get('required_improvements', [])
                if improvements:
                    feedback_section = f"""
이전 피드백:
{chr(10).join(f"- {improvement}" for improvement in improvements)}

위 피드백을 반영하여 개선된 요구사항을 작성하세요.
"""
            except:
                pass
        
        return f"""다음 FRS 문서를 분석하여 상세한 requirements.md를 생성하세요:

FRS 내용:
{frs_content}

서비스 유형: {service_type}

{feedback_section}

요구사항:
1. 구조화된 requirements.md 형식으로 작성
2. 명확한 요구사항 ID 체계 사용 (REQ-001, REQ-002 등)
3. 기능/비기능/기술 요구사항 분리
4. 수용 기준 포함
5. 한국어로 작성"""
    
    def _build_design_prompt(self, requirements_result: Dict, service_type: str) -> str:
        """설계 에이전트 프롬프트 - FRS 기반으로만 생성"""
        frs_content = self.context['project']['frs_content']
        
        return f"""다음 FRS를 바탕으로 design.md를 생성하세요 (Requirements 내용은 제외):

FRS 내용:
{frs_content}

서비스 유형: {service_type}

**중요**: Requirements 섹션(REQ-001 등)은 절대 포함하지 마세요. 오직 Design 관련 섹션만 작성하세요:
1. 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함 (```mermaid 블록)
3. 데이터 모델 정의
4. API 계약 설계
5. 보안 및 성능 고려사항
6. 한국어로 작성"""
    
    def _build_tasks_prompt(self, design_result: Dict) -> str:
        """작업 에이전트 프롬프트 - FRS 기반으로만 생성"""
        frs_content = self.context['project']['frs_content']
        
        return f"""다음 FRS를 바탕으로 tasks.md를 생성하세요 (Requirements/Design 내용은 제외):

FRS 내용:
{frs_content}

**중요**: Requirements나 Design 섹션은 포함하지 마세요. 오직 Tasks 관련 내용만 작성하세요:
1. Epic/Story/Task 계층 구조
2. 각 작업에 대한 명확한 설명
3. 예상 시간 및 우선순위
4. DoD (Definition of Done) 체크리스트
5. 의존성 표시
6. 한국어로 작성"""
    
    def _build_changes_prompt(self, service_type: str) -> str:
        """변경사항 에이전트 프롬프트 - FRS 기반으로만 생성"""
        frs_content = self.context['project']['frs_content']
        
        return f"""다음 FRS를 바탕으로 changes.md를 생성하세요 (Requirements/Design 내용은 제외):

FRS 내용:
{frs_content}

서비스 유형: {service_type}

**중요**: Requirements나 Design 섹션은 포함하지 마세요. 오직 Changes 관련 내용만 작성하세요:
1. 버전 이력
2. 변경 사항 요약
3. 영향도 및 위험 분석
4. 롤백 계획
5. 알려진 이슈
6. 한국어로 작성"""
    
    def _build_openapi_prompt(self, requirements_result: Dict, design_result: Dict) -> str:
        """OpenAPI 에이전트 프롬프트 - FRS 기반으로만 생성"""
        frs_content = self.context['project']['frs_content']
        
        return f"""다음 FRS를 바탕으로 OpenAPI 3.1 명세를 생성하세요:

FRS 내용:
{frs_content}

**중요**: Requirements나 Design 내용은 포함하지 마세요. 오직 API 명세만 작성하세요:

요구사항:
1. 유효한 JSON 형식 (마크다운 블록 없이)
2. OpenAPI 3.1 스펙 준수
3. 5-10개의 핵심 엔드포인트
4. 요청/응답 스키마 포함
5. 인증 및 오류 처리
6. JSON만 출력 (설명 없음)"""
    
    def _build_quality_prompt(self, results: Dict) -> str:
        """품질 평가 에이전트 프롬프트"""
        documents = []
        for name, result in results.items():
            if name in ['requirements', 'design', 'tasks', 'changes', 'openapi']:
                content = self._extract_content_from_result(result)
                documents.append(f"=== {name.upper()} ===\n{content[:1500]}")
        
        docs_text = "\n\n".join(documents)
        
        return f"""다음 생성된 문서들을 품질 평가하세요:

{docs_text}

각 항목을 0-100점으로 평가하고 JSON 형식으로 응답하세요."""
    
    def _build_consistency_prompt(self, results: Dict) -> str:
        """일관성 검증 에이전트 프롬프트"""
        documents = []
        for name, result in results.items():
            if name in ['requirements', 'design', 'tasks', 'changes', 'openapi']:
                content = self._extract_content_from_result(result)
                documents.append(f"=== {name.upper()} ===\n{content[:1500]}")
        
        docs_text = "\n\n".join(documents)
        
        return f"""다음 문서들 간의 일관성을 검증하세요:

{docs_text}

교차 참조, 명명 일관성, 구조적 일관성을 확인하고 JSON 형식으로 응답하세요."""
    
    def _build_coordinator_prompt(self, results: Dict) -> str:
        """코디네이터 에이전트 프롬프트"""
        quality_data = results.get('quality_assessor', {})
        consistency_data = results.get('consistency_checker', {})
        
        quality_content = self._extract_content_from_result(quality_data)
        consistency_content = self._extract_content_from_result(consistency_data)
        
        return f"""품질 평가와 일관성 검증 결과를 바탕으로 최종 승인 여부를 결정하세요:

품질 평가 결과:
{quality_content}

일관성 검증 결과:
{consistency_content}

승인 기준 (전체 품질 85점 이상, 일관성 이슈 5개 미만, high 심각도 이슈 없음)을 바탕으로 JSON 형식으로 결정하세요."""
    
    def _extract_content_from_result(self, result: Dict) -> str:
        """결과에서 컨텐츠 추출"""
        if isinstance(result, dict):
            return result.get('content', str(result))
        return str(result)
    
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
        """개별 에이전트 문서 즉시 저장 (비동기 버전)"""
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
    
    def _save_agent_document_sync(self, agent_name: str, content: str) -> Optional[Dict[str, Any]]:
        """개별 에이전트 문서 즉시 저장 (동기 버전)"""
        try:
            output_dir = self.context['project']['output_dir']
            
            # 파일명 결정
            if agent_name == 'openapi':
                filename = 'apis.json'
            else:
                filename = f'{agent_name}.md'
            
            # 파일 경로 설정
            file_path = Path(output_dir) / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 기존 파일 존재 여부 확인
            is_update = file_path.exists()
            action = "업데이트" if is_update else "생성"
            
            # 파일 저장
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            file_size = file_path.stat().st_size
            
            print(f"  📁 {filename} {action} 완료 ({file_size} bytes)")
            print(f"     💾 위치: {file_path}")
            
            # 저장된 파일 목록에 추가 (중복 방지)
            file_path_str = str(file_path)
            if file_path_str not in self.saved_files:
                self.saved_files.append(file_path_str)
            
            return {
                "filename": filename,
                "file_path": file_path_str,
                "size": file_size,
                "action": action
            }
                
        except Exception as e:
            print(f"  ❌ {agent_name} 문서 저장 중 오류: {str(e)}")
            return None
    
    async def _save_graph_results(self, graph_result: Any, service_type: ServiceType):
        """Graph 실행 결과를 파일로 저장"""
        try:
            print("📊 Graph 결과 분석 중...")
            
            # Graph 결과에서 문서 내용 추출
            # Strands Graph는 실행 중 생성된 모든 노드의 결과를 포함할 수 있음
            documents_to_save = ['requirements', 'design', 'tasks', 'changes']
            if service_type == ServiceType.API:
                documents_to_save.append('openapi')
            
            # Graph 결과에서 각 문서 내용 추출 및 저장
            for doc_type in documents_to_save:
                try:
                    # Graph 결과는 다양한 형태일 수 있으므로 안전하게 접근
                    content = self._extract_document_from_graph_result(graph_result, doc_type)
                    if content:
                        save_result = self._save_agent_document_sync(doc_type, content)
                        if save_result:
                            print(f"  📁 {save_result['filename']} {save_result['action']} 완료")
                        else:
                            print(f"  ⚠️ {doc_type} 저장 실패")
                    else:
                        print(f"  ⚠️ {doc_type} 내용을 Graph 결과에서 찾을 수 없음")
                except Exception as e:
                    print(f"  ❌ {doc_type} 저장 중 오류: {str(e)}")
            
            print("✅ Graph 결과 파일 저장 완료")
            
        except Exception as e:
            print(f"❌ Graph 결과 저장 실패: {str(e)}")
    
    def _extract_document_from_graph_result(self, graph_result: Any, doc_type: str) -> str:
        """Graph 결과에서 특정 문서 타입의 최신 내용 추출 (피드백 루프 반영)"""
        try:
            print(f"🔍 Graph 결과에서 {doc_type} 추출 중...")
            
            # Graph 결과에서 노드별 실행 기록 확인
            if hasattr(graph_result, 'results') and doc_type in graph_result.results:
                node_results = graph_result.results[doc_type]
                print(f"  📊 {doc_type} 노드 실행 횟수: {len(node_results) if isinstance(node_results, list) else '1'}")
                
                # 리스트 형태라면 마지막(최신) 결과 가져오기
                if isinstance(node_results, list) and len(node_results) > 0:
                    latest_result = node_results[-1]  # 마지막 실행 결과
                    print(f"  🎯 {doc_type} 최신 결과 사용 (인덱스: {len(node_results)-1})")
                    
                    if hasattr(latest_result, 'result'):
                        content = self._extract_content_from_agent_result(latest_result.result)
                        print(f"  📝 {doc_type} 내용 길이: {len(content)}")
                        return content
                    else:
                        content = str(latest_result)
                        print(f"  📝 {doc_type} 내용 길이: {len(content)}")
                        return content
                        
                # 단일 결과인 경우
                elif not isinstance(node_results, list):
                    print(f"  🎯 {doc_type} 단일 결과 사용")
                    if hasattr(node_results, 'result'):
                        content = self._extract_content_from_agent_result(node_results.result)
                        print(f"  📝 {doc_type} 내용 길이: {len(content)}")
                        return content
                    else:
                        content = str(node_results)
                        print(f"  📝 {doc_type} 내용 길이: {len(content)}")
                        return content
            
            # Graph 결과가 딕셔너리인 경우 (백업 방법)
            if isinstance(graph_result, dict):
                if doc_type in graph_result:
                    content = str(graph_result[doc_type])
                    print(f"  📝 {doc_type} 딕셔너리에서 추출, 길이: {len(content)}")
                    return content
                
                # 네스팅된 구조에서 찾기
                for key, value in graph_result.items():
                    if doc_type in key.lower():
                        content = str(value)
                        print(f"  📝 {doc_type} 네스팅에서 추출, 길이: {len(content)}")
                        return content
            
            print(f"  ⚠️ {doc_type} 내용을 Graph 결과에서 찾을 수 없음")
            return ""
            
        except Exception as e:
            print(f"  ⚠️ {doc_type} 추출 중 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _extract_content_from_agent_result(self, agent_result):
        """에이전트 결과에서 실제 내용 추출"""
        try:
            # AgentResult 객체에서 content 추출
            if hasattr(agent_result, 'message') and hasattr(agent_result.message, 'content'):
                content_list = agent_result.message.content
                if isinstance(content_list, list) and len(content_list) > 0:
                    # 첫 번째 content의 text 가져오기
                    first_content = content_list[0]
                    if hasattr(first_content, 'text'):
                        return str(first_content.text)
                    else:
                        return str(first_content)
                else:
                    return str(content_list)
            else:
                return str(agent_result)
        except Exception as e:
            print(f"  ⚠️ AgentResult 내용 추출 오류: {str(e)}")
            return str(agent_result)
    
    # === 파일 기반 컨텍스트 시스템 ===
    
    def _load_context_from_files(self, needed_files: List[str]) -> str:
        """저장된 파일에서 필요한 컨텍스트만 로드하여 메모리 부담 감소"""
        try:
            context_parts = []
            
            for file_type in needed_files:
                if file_type == 'openapi':
                    file_path = self.output_dir / 'apis.json'
                else:
                    file_path = self.output_dir / f'{file_type}.md'
                
                if file_path.exists():
                    content = file_path.read_text(encoding='utf-8')
                    if content.strip():  # 빈 파일 제외
                        context_parts.append(f"## {file_type.upper()}\n{content.strip()}")
                        print(f"  📖 {file_type} 파일 컨텍스트 로드 ({len(content)} chars)")
                    else:
                        print(f"  ⚠️ {file_type} 파일이 비어있음")
                else:
                    print(f"  ⚠️ {file_type} 파일이 존재하지 않음: {file_path}")
            
            if context_parts:
                combined_context = "\n\n".join(context_parts)
                print(f"  ✅ 총 {len(needed_files)}개 파일에서 {len(combined_context)} chars 컨텍스트 로드")
                return combined_context
            else:
                print(f"  ⚠️ 로드할 수 있는 파일이 없음")
                return ""
                
        except Exception as e:
            print(f"  ❌ 파일 컨텍스트 로드 실패: {str(e)}")
            return ""
    
    def _get_agent_dependencies(self, agent_name: str) -> List[str]:
        """에이전트별로 필요한 파일 의존성 반환"""
        dependency_map = {
            'requirements': [],  # FRS 내용만 필요
            'design': ['requirements'],
            'tasks': ['requirements', 'design'], 
            'changes': ['requirements', 'design', 'tasks'],
            'openapi': ['requirements', 'design', 'tasks'],
            'quality_assessor': ['requirements', 'design', 'tasks', 'changes', 'openapi'],
            'consistency_checker': ['requirements', 'design', 'tasks', 'changes', 'openapi'],
            'coordinator': ['requirements', 'design', 'tasks', 'changes', 'openapi']
        }
        
        return dependency_map.get(agent_name, [])
    
    def _inject_file_context(self, agent_name: str, base_prompt: str) -> str:
        """에이전트별로 필요한 파일 컨텍스트만 주입하여 토큰 효율성 극대화"""
        try:
            print(f"🔄 {agent_name} 에이전트 컨텍스트 주입 중...")
            
            needed_files = self._get_agent_dependencies(agent_name)
            
            if needed_files:
                file_context = self._load_context_from_files(needed_files)
                
                if file_context:
                    # 기존 플레이스홀더를 실제 파일 컨텍스트로 교체
                    if '[FILE_CONTEXT_PLACEHOLDER]' in base_prompt:
                        enhanced_prompt = base_prompt.replace('[FILE_CONTEXT_PLACEHOLDER]', file_context)
                    else:
                        # 플레이스홀더가 없으면 끝에 추가
                        enhanced_prompt = f"{base_prompt}\n\n## 참조 문서\n{file_context}"
                    
                    print(f"  ✅ {agent_name} 컨텍스트 주입 완료 ({len(enhanced_prompt)} chars)")
                    return enhanced_prompt
                else:
                    print(f"  ⚠️ {agent_name} 사용 가능한 파일 컨텍스트 없음")
                    return base_prompt
            else:
                print(f"  ℹ️ {agent_name} 파일 의존성 없음 (FRS만 사용)")
                return base_prompt
                
        except Exception as e:
            print(f"  ❌ {agent_name} 컨텍스트 주입 실패: {str(e)}")
            return base_prompt
    
    async def _collect_and_save_node_results(self, graph, service_type: ServiceType) -> List[str]:
        """Graph의 각 노드 결과를 수집하고 파일로 저장"""
        saved_files = []
        
        try:
            # Graph 객체에서 노드별 결과 접근
            nodes_to_save = ['requirements', 'design', 'tasks', 'changes']
            if service_type == ServiceType.API:
                nodes_to_save.append('openapi')
            
            for node_name in nodes_to_save:
                try:
                    # Graph의 노드에서 결과 가져오기
                    node_result = self._get_node_result(graph, node_name)
                    
                    if node_result:
                        # 결과 텍스트 처리
                        processed_result = self._process_agent_result(node_name, node_result)
                        
                        # 파일 저장
                        save_result = self._save_agent_document_sync(node_name, processed_result)
                        if save_result:
                            saved_files.append(save_result['file_path'])
                            print(f"  📁 {save_result['filename']} {save_result['action']} 완료")
                        else:
                            print(f"  ❌ {node_name} 저장 실패")
                    else:
                        print(f"  ⚠️ {node_name} 노드 결과 없음")
                        
                except Exception as e:
                    print(f"  ❌ {node_name} 처리 중 오류: {str(e)}")
            
            print(f"✅ 총 {len(saved_files)}개 파일 저장 완료")
            return saved_files
            
        except Exception as e:
            print(f"❌ 노드 결과 수집 실패: {str(e)}")
            return saved_files
    
    def _get_node_result(self, graph, node_name: str):
        """Graph에서 특정 노드의 결과 가져오기"""
        try:
            # Graph 객체의 내부 구조에서 노드 결과 접근
            if hasattr(graph, 'nodes'):
                for node in graph.nodes:
                    if hasattr(node, 'node_id') and node.node_id == node_name:
                        if hasattr(node, 'result'):
                            return node.result
            
            # 다른 방식으로 접근 시도
            if hasattr(graph, '_nodes'):
                node = graph._nodes.get(node_name)
                if node and hasattr(node, 'result'):
                    return node.result
            
            # 마지막 실행 결과에서 찾기
            if hasattr(graph, 'last_execution_result'):
                return graph.last_execution_result
                
            return None
            
        except Exception as e:
            print(f"  ⚠️ {node_name} 노드 결과 접근 실패: {str(e)}")
            return None
    
    async def _generate_remaining_documents(self, requirements_content: str, service_type: ServiceType) -> List[str]:
        """requirements.md를 기반으로 나머지 문서들 생성"""
        saved_files = []
        
        try:
            # 나머지 생성할 문서들
            remaining_agents = ['design', 'tasks', 'changes']
            if service_type == ServiceType.API:
                remaining_agents.append('openapi')
            
            current_content = {'requirements': requirements_content}
            
            for agent_name in remaining_agents:
                try:
                    print(f"🔄 {agent_name} 문서 생성 중...")
                    
                    # 에이전트별 프롬프트 생성
                    prompt = self._build_agent_prompt_from_previous(agent_name, current_content, service_type.value)
                    
                    # 에이전트 실행
                    agent = self.agents[agent_name]
                    result = agent(prompt)
                    
                    # 결과 처리
                    result_text = self._process_agent_result(agent_name, result)
                    current_content[agent_name] = result_text
                    
                    # 파일 저장
                    save_result = self._save_agent_document_sync(agent_name, result_text)
                    if save_result:
                        saved_files.append(save_result['file_path'])
                        print(f"  📁 {save_result['filename']} {save_result['action']} 완료")
                    else:
                        print(f"  ❌ {agent_name} 저장 실패")
                    
                except Exception as e:
                    print(f"  ❌ {agent_name} 생성 중 오류: {str(e)}")
                    continue
            
            return saved_files
            
        except Exception as e:
            print(f"❌ 나머지 문서 생성 실패: {str(e)}")
            return saved_files
    
    def _build_agent_prompt_from_previous(self, agent_name: str, previous_contents: Dict[str, str], service_type: str) -> str:
        """이전 생성 결과를 기반으로 에이전트별 프롬프트 생성"""
        
        if agent_name == 'design':
            requirements = previous_contents.get('requirements', '')[:3000]
            return f"""다음 요구사항을 바탕으로 상세한 design.md를 생성하세요:

요구사항:
{requirements}

서비스 유형: {service_type}

요구사항:
1. 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함 (```mermaid 블록)
3. 데이터 모델 정의
4. API 계약 설계
5. 보안 및 성능 고려사항
6. 한국어로 작성"""
        
        elif agent_name == 'tasks':
            design = previous_contents.get('design', '')[:3000]
            return f"""다음 설계를 바탕으로 상세한 tasks.md를 생성하세요:

설계:
{design}

요구사항:
1. Epic/Story/Task 계층 구조
2. 각 작업에 대한 명확한 설명
3. 예상 시간 및 우선순위
4. DoD (Definition of Done) 체크리스트
5. 의존성 표시
6. 한국어로 작성"""
        
        elif agent_name == 'changes':
            return f"""프로젝트 배포를 위한 상세한 changes.md를 생성하세요:

서비스 유형: {service_type}

요구사항:
1. 버전 이력
2. 변경 사항 요약
3. 영향도 및 위험 분석
4. 롤백 계획
5. 알려진 이슈
6. 한국어로 작성"""
        
        elif agent_name == 'openapi':
            requirements = previous_contents.get('requirements', '')[:2000]
            design = previous_contents.get('design', '')[:2000]
            return f"""OpenAPI 3.1 명세를 JSON 형식으로 생성하세요:

요구사항:
{requirements}

설계:
{design}

요구사항:
1. 유효한 JSON 형식 (마크다운 블록 없이)
2. OpenAPI 3.1 스펙 준수
3. 5-10개의 핵심 엔드포인트
4. 요청/응답 스키마 포함
5. 인증 및 오류 처리
6. JSON만 출력 (설명 없음)"""
        
        return "작업을 수행하세요."
    
    
    
    
    
    
    
    
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