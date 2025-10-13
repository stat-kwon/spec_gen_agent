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


from .config import Config
from .models import ServiceType
from .tools import (
    load_frs_document,
    write_spec_file,
    create_git_branch,
    commit_changes,
    validate_markdown_structure,
    validate_openapi_spec,
    apply_template,
)
from .agents.spec_agents import (
    create_requirements_agent,
    create_design_agent,
    create_tasks_agent,
    create_changes_agent,
    create_openapi_agent
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
            'documents': {
                'previous_contents': {},
                'template_results': {},
            },
            'quality': {},
            'metrics': {},
        }
        
        # 에이전트 컨테이너
        self.agents = {}
        
        # 저장된 파일 목록 추적
        self.saved_files = []
        
        # 세션 ID 생성
        self.session_id = f"spec-{int(time.time())}"
        
        print("✅ 워크플로우 초기화 완료")
    
    def _initialize_agents(self):
        """에이전트 초기화"""
        print("🤖 에이전트 초기화 중...")
        
        # 기본 문서 생성 에이전트들
        self.agents = {
            'requirements': create_requirements_agent(self.config),
            'design': create_design_agent(self.config),
            'tasks': create_tasks_agent(self.config),
            'changes': create_changes_agent(self.config),
            'openapi': create_openapi_agent(self.config)
        }
        
        print(f"✅ {len(self.agents)}개 에이전트 초기화 완료")
    
    
    
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
            
            # 4. 순차적 파일 기반 워크플로우 실행
            print("\n🔄 순차적 파일 기반 워크플로우 시작...")
            workflow_result = await self._execute_sequential_workflow(service_type)
            
            # 5. 저장된 파일 목록 수집
            files_written = workflow_result.get('saved_files', [])
            
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
                "workflow_result": workflow_result,
                "execution_time": execution_time,
                "framework": "Strands Agent SDK - Sequential"
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
    
    async def _execute_sequential_workflow(self, service_type: ServiceType) -> Dict[str, Any]:
        """순차적 파일 기반 워크플로우 실행"""
        
        print("🚀 순차적 파일 기반 워크플로우 시작...")
        
        try:
            saved_files = []
            
            # 1. Requirements 생성
            print("🔄 Requirements 생성 중...")
            frs_content = self.context['project']['frs_content']
            req_prompt = self._build_requirements_prompt(frs_content, service_type.value, {})
            req_result = self.agents['requirements'](req_prompt)
            req_content = self._process_agent_result('requirements', req_result)
            self._validate_and_record_template('requirements', req_content)

            save_result = self._save_agent_document_sync('requirements', req_content)
            if save_result:
                saved_files.append(save_result['file_path'])
            
            output_dir = str(Path(self.context['project']['output_dir']).resolve())

            # 2. Design 생성
            print("🔄 Design 생성 중...")
            design_prompt = self._build_design_prompt({}, service_type.value, output_dir)
            design_result = self.agents['design'](design_prompt)
            design_content = self._process_agent_result('design', design_result)
            self._validate_and_record_template('design', design_content)

            save_result = self._save_agent_document_sync('design', design_content)
            if save_result:
                saved_files.append(save_result['file_path'])

            # 3. Tasks 생성
            print("🔄 Tasks 생성 중...")
            tasks_prompt = self._build_tasks_prompt({}, output_dir)
            tasks_result = self.agents['tasks'](tasks_prompt)
            tasks_content = self._process_agent_result('tasks', tasks_result)
            self._validate_and_record_template('tasks', tasks_content)

            save_result = self._save_agent_document_sync('tasks', tasks_content)
            if save_result:
                saved_files.append(save_result['file_path'])

            # 4. Changes 생성
            print("🔄 Changes 생성 중...")
            changes_prompt = self._build_changes_prompt(service_type.value, output_dir)
            changes_result = self.agents['changes'](changes_prompt)
            changes_content = self._process_agent_result('changes', changes_result)
            self._validate_and_record_template('changes', changes_content)

            save_result = self._save_agent_document_sync('changes', changes_content)
            if save_result:
                saved_files.append(save_result['file_path'])

            # 5. OpenAPI 생성 (API 서비스인 경우만)
            if service_type == ServiceType.API:
                print("🔄 OpenAPI 생성 중...")
                openapi_prompt = self._build_openapi_prompt({}, {}, output_dir)
                openapi_result = self.agents['openapi'](openapi_prompt)
                openapi_content = self._process_agent_result('openapi', openapi_result)
                self._validate_and_record_template('openapi', openapi_content)

                save_result = self._save_agent_document_sync('openapi', openapi_content)
                if save_result:
                    saved_files.append(save_result['file_path'])
            
            return {
                'success': True,
                'saved_files': saved_files,
                'execution_type': 'sequential'
            }
            
        except Exception as e:
            print(f"❌ 순차적 워크플로우 실패: {str(e)}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    
    
    
    
    
    
    
    
    
    
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
    
    def _build_design_prompt(self, requirements_result: Dict, service_type: str, output_dir: str) -> str:
        """설계 에이전트 프롬프트 - 파일 기반"""
        requirements_file = str(Path(output_dir) / "requirements.md")

        return f"""다음 요구사항 파일을 읽어서 상세한 design.md를 생성하세요:

요구사항 파일을 확인하려면 read_spec_file("{requirements_file}")를 호출하세요.
서비스 유형: {service_type}

요구사항:
1. 시스템 아키텍처 설계
2. Mermaid 시퀀스 다이어그램 포함 (```mermaid 블록)
3. 데이터 모델 정의
4. API 계약 설계
5. 보안 및 성능 고려사항
6. 한국어로 작성

지침: read_spec_file("{requirements_file}")로 불러온 내용을 바탕으로 설계 문서를 작성하세요."""

    def _build_tasks_prompt(self, design_result: Dict, output_dir: str) -> str:
        """작업 에이전트 프롬프트 - 파일 기반"""
        design_file = str(Path(output_dir) / "design.md")

        return f"""다음 설계 파일을 읽어서 상세한 tasks.md를 생성하세요:

설계 파일을 확인하려면 read_spec_file("{design_file}")를 호출하세요.

요구사항:
1. Epic/Story/Task 계층 구조
2. 각 작업에 대한 명확한 설명
3. 예상 시간 및 우선순위
4. DoD (Definition of Done) 체크리스트
5. 의존성 표시
6. 한국어로 작성

지침: read_spec_file("{design_file}")로 불러온 내용을 바탕으로 작업 분해 문서를 작성하세요."""

    def _build_changes_prompt(self, service_type: str, output_dir: str) -> str:
        """변경사항 에이전트 프롬프트"""
        requirements_file = str(Path(output_dir) / "requirements.md")
        design_file = str(Path(output_dir) / "design.md")
        tasks_file = str(Path(output_dir) / "tasks.md")

        return f"""프로젝트 배포를 위한 상세한 changes.md를 생성하세요:

서비스 유형: {service_type}

참고 문서:
- Requirements: read_spec_file("{requirements_file}")
- Design: read_spec_file("{design_file}")
- Tasks: read_spec_file("{tasks_file}")

요구사항:
1. 버전 이력
2. 변경 사항 요약
3. 영향도 및 위험 분석
4. 롤백 계획
5. 알려진 이슈
6. 한국어로 작성"""

    def _build_openapi_prompt(self, requirements_result: Dict, design_result: Dict, output_dir: str) -> str:
        """OpenAPI 에이전트 프롬프트 - 파일 기반"""
        requirements_file = str(Path(output_dir) / "requirements.md")
        design_file = str(Path(output_dir) / "design.md")

        return f"""Create a complete OpenAPI 3.1 specification in JSON format.

Use read_spec_file("{requirements_file}") and read_spec_file("{design_file}") to load the source material before writing the specification.

IMPORTANT:
1. Read the contents of both files first
2. Respond with only valid JSON. Start with {{ and end with }}
3. Include:
   - OpenAPI 3.1.0 specification
   - Complete info section with title, version, description
   - All authentication schemes (Bearer JWT)
   - 5-10 core endpoints based on requirements
   - Detailed request/response schemas
   - Error responses (400, 401, 404, 500)
   - Components section with reusable schemas

Output pure JSON only - no text before or after."""
    
    
    
    
    
    def _process_agent_result(self, agent_name: str, result: Any) -> str:
        """에이전트 결과 처리"""
        if agent_name == 'openapi' and isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)

        result_str = str(result)

        # OpenAPI JSON인 경우 마크다운 블록 제거 및 JSON 검증
        if agent_name == 'openapi':
            # ```json 블록 제거
            if result_str.startswith('```json'):
                result_str = result_str[7:]
            if result_str.startswith('```'):
                result_str = result_str[3:]
            if result_str.endswith('```'):
                result_str = result_str[:-3]
            result_str = result_str.strip()

            try:
                parsed = json.loads(result_str)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "OpenAPI 결과를 JSON으로 파싱하는 데 실패했습니다: "
                    f"{exc.msg} (line {exc.lineno}, column {exc.colno})"
                ) from exc

            return json.dumps(parsed, ensure_ascii=False, indent=2)

        return result_str


    def _validate_and_record_template(self, agent_name: str, content: str) -> Dict[str, Any]:
        """apply_template 도구로 결과를 검증하고 컨텍스트에 저장"""

        template_type = 'openapi' if agent_name == 'openapi' else agent_name

        try:
            if agent_name == 'openapi':
                template_result = validate_openapi_spec(content)
            else:
                template_result = apply_template(content, template_type)
        except Exception as e:
            print(f"  ❌ {agent_name} 템플릿 검증 도구 호출 실패: {str(e)}")
            raise

        # 컨텍스트에 결과 기록
        self.context['documents'].setdefault('previous_contents', {})[agent_name] = content
        self.context['documents'].setdefault('template_results', {})[agent_name] = template_result
        self.context['metrics'].setdefault('template_checks', {})[agent_name] = template_result

        if not isinstance(template_result, dict):
            raise ValueError(f"템플릿 검증 결과가 올바르지 않습니다: {template_result}")

        if not template_result.get('success', False):
            missing_sections = template_result.get('missing_sections', [])
            error_message = template_result.get('error')
            detail = ''
            if error_message:
                detail = error_message
            elif missing_sections:
                detail = f"누락된 섹션: {', '.join(missing_sections)}"
            else:
                detail = "템플릿 검증에 실패했습니다."

            print(f"  ❌ {agent_name} 템플릿 검증 실패: {detail}")
            raise ValueError(f"{agent_name} 템플릿 검증 실패: {detail}")

        return template_result


    async def _save_agent_document(self, agent_name: str, content: str) -> Optional[Dict[str, Any]]:
        """개별 에이전트 문서 즉시 저장 (비동기 버전)"""
        try:
            output_dir = self.context['project']['output_dir']

            # 파일명 결정
            if agent_name == 'openapi':
                filename = 'openapi.json'
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
                filename = 'openapi.json'
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

                        self._validate_and_record_template(node_name, processed_result)

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

                    self._validate_and_record_template(agent_name, result_text)

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
                "openapi.json"
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