"""
실용적인 Strands Agent SDK 기반 워크플로우
복잡한 state 관리 없이 필요한 기능만 포함
"""


import inspect
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
import time
import json


from .config import Config
from .models import ServiceType
from .logging_utils import configure_logging, get_agent_logger, get_session_logger
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
    create_openapi_agent,
    create_quality_assessor_agent,
    create_consistency_checker_agent,
    create_coordinator_agent,
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
        self.agents: Dict[str, Any] = {}

        # 저장된 파일 목록 추적
        self.saved_files: List[str] = []

        # 세션 ID 생성 및 로거 구성
        self.session_id = f"spec-{int(time.time())}"
        configure_logging(self.config.log_level)
        self.logger = get_session_logger("workflow", self.session_id)
        self._agent_loggers: Dict[str, logging.LoggerAdapter] = {}

        self.logger.info("워크플로우 초기화 완료")

    def _tool_kwargs(self, tool_fn):
        """도구 함수 호출 시 session_id 지원 여부에 따라 kwargs 제공"""

        try:
            signature = inspect.signature(tool_fn)
        except (TypeError, ValueError):
            return {}

        if "session_id" in signature.parameters:
            return {"session_id": self.session_id}

        return {}
    
    def _initialize_agents(self):
        """에이전트 초기화"""
        self.logger.info("에이전트 초기화 시작")

        # 기본 문서 생성 에이전트들
        self.agents = {
            'requirements': create_requirements_agent(self.config, session_id=self.session_id),
            'design': create_design_agent(self.config, session_id=self.session_id),
            'tasks': create_tasks_agent(self.config, session_id=self.session_id),
            'changes': create_changes_agent(self.config, session_id=self.session_id),
            'openapi': create_openapi_agent(self.config, session_id=self.session_id),
            'quality_assessor': create_quality_assessor_agent(self.config),
            'consistency_checker': create_consistency_checker_agent(self.config),
            'coordinator': create_coordinator_agent(self.config),
        }

        self._agent_loggers = {
            name: get_agent_logger(self.session_id, name)
            for name in self.agents
        }

        self.logger.info("%d개 에이전트 초기화 완료", len(self.agents))

    def _get_agent_logger(self, agent_name: str) -> logging.LoggerAdapter:
        """세션 컨텍스트와 함께 에이전트 로거를 반환합니다."""

        if agent_name not in self._agent_loggers:
            self._agent_loggers[agent_name] = get_agent_logger(self.session_id, agent_name)
        return self._agent_loggers[agent_name]



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
            self.logger.info("FRS 로드 시작 | 경로: %s", frs_path)
            await self._initialize_project(frs_path, service_type, output_dir)
            self.logger.info("FRS 로드 완료 | 서비스 유형: %s", service_type.value)

            # 2. Git 브랜치 생성 (선택적)
            if use_git:
                await self._setup_git_branch()

            # 3. 에이전트 초기화
            self._initialize_agents()

            # 4. 순차적 파일 기반 워크플로우 실행
            self.logger.info("순차적 파일 기반 워크플로우 시작")
            workflow_result = await self._execute_sequential_workflow(service_type)

            # 4-1. 문서 품질 보강 사이클 실행
            if workflow_result.get('success'):
                quality_cycle_result = await self._run_quality_improvement_cycle(service_type)
            else:
                quality_cycle_result = {
                    'iterations': [],
                    'improvement_applied': False,
                    'updated_files': [],
                    'skipped': True,
                    'reason': 'sequential_generation_failed',
                }

            # 5. 저장된 파일 목록 수집
            files_written = list(dict.fromkeys(self.saved_files)) if self.saved_files else workflow_result.get('saved_files', [])

            # 6. Git 커밋 (선택적)
            if use_git and files_written:
                await self._commit_changes(files_written)
            
            # 7. 결과 반환
            execution_time = time.time() - start_time
            self.logger.info(
                "워크플로우 완료 | 생성 파일 %d개 | 실행 시간 %.2f초",
                len(files_written),
                execution_time,
            )

            return {
                "success": True,
                "session_id": self.session_id,
                "output_dir": self.context['project']['output_dir'],
                "files_written": files_written,
                "workflow_result": workflow_result,
                "quality_cycle": quality_cycle_result,
                "execution_time": execution_time,
                "framework": "Strands Agent SDK - Sequential"
            }

        except Exception as e:
            error_msg = f"워크플로우 실행 실패: {str(e)}"
            self.logger.exception("워크플로우 실행 실패")

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
        frs_result = load_frs_document(
            frs_path,
            **self._tool_kwargs(load_frs_document),
        )
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
        self.logger.info("출력 디렉토리 준비 완료 | 경로: %s", self.context['project']['output_dir'])
    
    async def _setup_git_branch(self):
        """Git 브랜치 설정"""
        frs_id = self.context['project']['frs_id']
        service_type = self.context['project']['service_type']
        
        git_result = create_git_branch(
            frs_id,
            service_type,
            **self._tool_kwargs(create_git_branch),
        )
        if git_result.get("success"):
            self.logger.info("Git 브랜치 생성 완료 | 이름: %s", git_result.get('branch_name'))
        else:
            self.logger.warning("Git 브랜치 생성 실패 | 이유: %s", git_result.get('error'))
    
    async def _execute_sequential_workflow(self, service_type: ServiceType) -> Dict[str, Any]:
        """순차적 파일 기반 워크플로우 실행"""

        self.logger.info("순차적 파일 기반 워크플로우 실행 시작")

        try:
            saved_files = []

            # 1. Requirements 생성
            requirements_logger = self._get_agent_logger('requirements')
            requirements_logger.info("문서 생성 시작")
            frs_content = self.context['project']['frs_content']
            req_prompt = self._build_requirements_prompt(frs_content, service_type.value, {})
            req_result = self.agents['requirements'](req_prompt)
            req_content = self._process_agent_result('requirements', req_result)
            self._validate_and_record_template('requirements', req_content)

            save_result = self._save_agent_document_sync('requirements', req_content)
            if save_result:
                saved_files.append(save_result['file_path'])
                requirements_logger.info("문서 생성 완료 | 파일: %s", save_result['file_path'])
            else:
                requirements_logger.warning("문서 저장 실패")

            output_dir = str(Path(self.context['project']['output_dir']).resolve())

            # 2. Design 생성
            design_logger = self._get_agent_logger('design')
            design_logger.info("문서 생성 시작")
            design_prompt = self._build_design_prompt({}, service_type.value, output_dir)
            design_result = self.agents['design'](design_prompt)
            design_content = self._process_agent_result('design', design_result)
            self._validate_and_record_template('design', design_content)

            save_result = self._save_agent_document_sync('design', design_content)
            if save_result:
                saved_files.append(save_result['file_path'])
                design_logger.info("문서 생성 완료 | 파일: %s", save_result['file_path'])
            else:
                design_logger.warning("문서 저장 실패")

            # 3. Tasks 생성
            tasks_logger = self._get_agent_logger('tasks')
            tasks_logger.info("문서 생성 시작")
            tasks_prompt = self._build_tasks_prompt({}, output_dir)
            tasks_result = self.agents['tasks'](tasks_prompt)
            tasks_content = self._process_agent_result('tasks', tasks_result)
            self._validate_and_record_template('tasks', tasks_content)

            save_result = self._save_agent_document_sync('tasks', tasks_content)
            if save_result:
                saved_files.append(save_result['file_path'])
                tasks_logger.info("문서 생성 완료 | 파일: %s", save_result['file_path'])
            else:
                tasks_logger.warning("문서 저장 실패")

            # 4. Changes 생성
            changes_logger = self._get_agent_logger('changes')
            changes_logger.info("문서 생성 시작")
            changes_prompt = self._build_changes_prompt(service_type.value, output_dir)
            changes_result = self.agents['changes'](changes_prompt)
            changes_content = self._process_agent_result('changes', changes_result)
            self._validate_and_record_template('changes', changes_content)

            save_result = self._save_agent_document_sync('changes', changes_content)
            if save_result:
                saved_files.append(save_result['file_path'])
                changes_logger.info("문서 생성 완료 | 파일: %s", save_result['file_path'])
            else:
                changes_logger.warning("문서 저장 실패")

            # 5. OpenAPI 생성 (API 서비스인 경우만)
            if service_type == ServiceType.API:
                openapi_logger = self._get_agent_logger('openapi')
                openapi_logger.info("문서 생성 시작")
                openapi_prompt = self._build_openapi_prompt({}, {}, output_dir)
                openapi_result = self.agents['openapi'](openapi_prompt)
                openapi_content = self._process_agent_result('openapi', openapi_result)
                self._validate_and_record_template('openapi', openapi_content)

                save_result = self._save_agent_document_sync('openapi', openapi_content)
                if save_result:
                    saved_files.append(save_result['file_path'])
                    openapi_logger.info("문서 생성 완료 | 파일: %s", save_result['file_path'])
                else:
                    openapi_logger.warning("문서 저장 실패")

            self.logger.info("순차적 워크플로우 종료 | 저장 파일 %d개", len(saved_files))
            return {
                'success': True,
                'saved_files': saved_files,
                'execution_type': 'sequential'
            }

        except Exception as e:
            self.logger.exception("순차적 워크플로우 실패")
            return {
                'success': False,
                'error': str(e)
            }

    async def _run_quality_improvement_cycle(self, service_type: ServiceType) -> Dict[str, Any]:
        """생성된 문서에 대한 품질 보강 사이클을 실행합니다."""

        self.logger.info("품질 개선 사이클 시작")

        cycle_results: List[Dict[str, Any]] = []
        improvement_applied = False
        cumulative_updated_files: List[str] = []
        max_iterations = max(1, getattr(self.config, "max_iterations", 1))

        for iteration in range(1, max_iterations + 1):
            documents = self._load_generated_documents(service_type)
            if not documents:
                self.logger.warning("품질 개선 사이클 중단 - 로드된 문서가 없습니다")
                break

            review_payload = self._format_documents_for_review(documents)

            quality_prompt = self._build_quality_review_prompt(review_payload)
            quality_raw = self.agents['quality_assessor'](quality_prompt)
            quality_result = self._parse_json_response('quality_assessor', quality_raw)

            consistency_prompt = self._build_consistency_review_prompt(review_payload)
            consistency_raw = self.agents['consistency_checker'](consistency_prompt)
            consistency_result = self._parse_json_response('consistency_checker', consistency_raw)

            coordinator_prompt = self._build_coordinator_prompt(
                review_payload,
                quality_result,
                consistency_result,
            )
            coordinator_raw = self.agents['coordinator'](coordinator_prompt)
            coordinator_result = self._parse_json_response('coordinator', coordinator_raw)

            iteration_result = {
                'iteration': iteration,
                'quality': quality_result,
                'consistency': consistency_result,
                'coordinator': coordinator_result,
            }
            cycle_results.append(iteration_result)

            if not self._should_continue_quality_loop(quality_result, coordinator_result):
                self.logger.info("품질 개선 사이클 종료 - 추가 개선 불필요")
                break

            feedback_items = self._aggregate_feedback(quality_result, consistency_result, coordinator_result)
            if not feedback_items:
                self.logger.info("품질 개선 사이클 종료 - 피드백이 없습니다")
                break

            updated_files = self._apply_feedback_to_documents(
                documents,
                feedback_items,
                service_type,
            )
            if not updated_files:
                self.logger.warning("품질 개선 사이클 - 문서 갱신 실패, 루프 종료")
                break

            improvement_applied = True
            cumulative_updated_files.extend(updated_files)

        result_summary = {
            'iterations': cycle_results,
            'improvement_applied': improvement_applied,
            'updated_files': list(dict.fromkeys(cumulative_updated_files)),
        }

        self.context['quality']['cycle_results'] = cycle_results
        self.context['quality']['improvement_applied'] = improvement_applied

        return result_summary

    
    
    
    
    
    
    
    
    
    
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
        output_dir = self.context['project']['output_dir']
        requirements_file = f"{output_dir}/requirements.md"

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
        output_dir = self.context['project']['output_dir']
        requirements_file = f"{output_dir}/requirements.md"
        design_file = f"{output_dir}/design.md"
        tasks_file = f"{output_dir}/tasks.md"


        return f"""프로젝트 배포를 위한 상세한 changes.md를 생성하세요:

요구사항 파일 경로: {requirements_file}
설계 파일 경로: {design_file}

서비스 유형: {service_type}

참고 문서:
- Requirements: read_spec_file("{requirements_file}")
- Design: read_spec_file("{design_file}")
- Tasks: read_spec_file("{tasks_file}")

반드시 아래 섹션 헤더를 동일한 형태(한글/영문 병기)로 포함하세요:
## 버전 이력/Version History
## 변경 요약/Change Summary
## 영향/위험/Impact/Risk
## 롤백 계획/Rollback Plan
## 알려진 문제/Known Issues

각 섹션에 구체적인 내용을 작성하고, 목록이나 표를 활용해 배포 계획을 명확히 표현하세요."""

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


    def _load_generated_documents(self, service_type: ServiceType) -> Dict[str, Dict[str, str]]:
        """현재 출력 디렉토리에서 생성된 문서를 로드합니다."""

        output_dir = Path(self.context.get('project', {}).get('output_dir', ""))
        if not output_dir:
            return {}

        documents: Dict[str, Dict[str, str]] = {}
        for agent_name in self._get_document_agent_order(service_type):
            filename = 'openapi.json' if agent_name == 'openapi' else f"{agent_name}.md"
            file_path = output_dir / filename
            if not file_path.exists():
                continue

            try:
                content = file_path.read_text(encoding='utf-8')
                documents[agent_name] = {
                    'path': str(file_path),
                    'content': content,
                }
            except Exception:
                self._get_agent_logger(agent_name).exception(
                    "문서 로드 실패 | 파일: %s",
                    str(file_path),
                )

        return documents

    def _format_documents_for_review(self, documents: Dict[str, Dict[str, str]]) -> str:
        """품질 에이전트에 전달할 문서 메타데이터를 포맷팅합니다."""

        output_dir = self.context.get('project', {}).get('output_dir', '')
        lines: List[str] = [f"검토 대상 문서 목록 (output_dir={output_dir}):"]
        for agent_name in ['requirements', 'design', 'tasks', 'changes', 'openapi']:
            doc = documents.get(agent_name)
            if not doc:
                continue

            title = 'openapi.json' if agent_name == 'openapi' else f"{agent_name}.md"
            lines.append(f"- {title}: {doc['path']}")

        return "\n".join(lines)

    def _build_quality_review_prompt(self, review_payload: str) -> str:
        """품질 평가 에이전트 프롬프트를 구성합니다."""

        return (
            "다음은 생성된 명세 문서 목록입니다. 각 문서의 실제 내용은 read_spec_file(path) 도구를 사용해 필요한 것만 읽으세요.\n"
            f"list_spec_files(\"{self.context.get('project', {}).get('output_dir', '')}\")를 호출하면 최신 파일 목록을 확인할 수 있습니다.\n\n"
            f"{review_payload}\n\n"
            "평가 후 반드시 JSON으로만 응답하세요. 필수 키: completeness, consistency, clarity, technical, overall, feedback (리스트), needs_improvement (불리언)."
        )

    def _build_consistency_review_prompt(self, review_payload: str) -> str:
        """일관성 검증 에이전트 프롬프트를 구성합니다."""

        return (
            "다음 문서 목록을 바탕으로 교차 검증을 수행하세요. 실제 내용은 필요한 문서만 read_spec_file(path)로 읽어 일관성을 확인하세요.\n"
            f"list_spec_files(\"{self.context.get('project', {}).get('output_dir', '')}\") 호출로 파일 현황을 확인할 수 있습니다.\n"
            "검토 후 JSON으로만 응답하세요.\n\n"
            f"{review_payload}\n\n"
            "필수 JSON 키: issues (리스트), severity (low|medium|high), cross_references (정수), naming_conflicts (정수)."
        )

    def _build_coordinator_prompt(
        self,
        review_payload: str,
        quality_result: Any,
        consistency_result: Any,
    ) -> str:
        """코디네이터 에이전트 프롬프트를 구성합니다."""

        quality_json = (
            json.dumps(quality_result, ensure_ascii=False, indent=2)
            if isinstance(quality_result, dict)
            else str(quality_result)
        )
        consistency_json = (
            json.dumps(consistency_result, ensure_ascii=False, indent=2)
            if isinstance(consistency_result, dict)
            else str(consistency_result)
        )

        output_dir = self.context.get('project', {}).get('output_dir', '')
        return (
            "다음은 생성된 문서 경로와 이전 평가 결과입니다. 필요 시 read_spec_file(path)으로 세부 내용을 확인한 뒤 최종 승인 여부를 JSON으로 판단하세요.\n"
            f"list_spec_files(\"{output_dir}\") 호출로 최신 문서 목록을 다시 확인할 수 있습니다.\n\n"
            f"문서 목록:\n{review_payload}\n\n"
            f"품질 평가 결과:\n{quality_json}\n\n"
            f"일관성 평가 결과:\n{consistency_json}\n\n"
            "JSON 키: approved (불리언), overall_quality (숫자), decision, required_improvements (리스트), message."
        )

    def _parse_json_response(self, agent_name: str, response: Any) -> Dict[str, Any]:
        """에이전트 응답을 JSON으로 파싱합니다."""

        if response is None:
            return {}

        if isinstance(response, dict):
            return response

        text = str(response).strip()
        if not text:
            return {}

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                first_line = lines.pop(0)
                if first_line.lower().startswith("```json"):
                    pass
            if lines and lines[-1].startswith("```"):
                lines.pop()
            text = "\n".join(lines).strip()

        decoder = json.JSONDecoder()
        try:
            return decoder.decode(text)
        except json.JSONDecodeError:
            # 선행/후행 자연어를 제거하고 첫 번째 JSON 오브젝트를 추출 시도
            for idx, ch in enumerate(text):
                if ch in "[{":
                    try:
                        parsed, _ = decoder.raw_decode(text[idx:])
                        return parsed
                    except json.JSONDecodeError:
                        continue

        self._get_agent_logger(agent_name).warning(
            "JSON 파싱 실패 - 원문을 raw_response로 저장합니다"
        )
        return {"raw_response": text}

    def _should_continue_quality_loop(
        self,
        quality_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> bool:
        """추가 품질 개선이 필요한지 판단합니다."""

        if not isinstance(quality_result, dict):
            return False

        needs_improvement = bool(quality_result.get('needs_improvement'))
        overall = quality_result.get('overall')
        quality_threshold = getattr(self.config, 'quality_threshold', 0.0)
        below_threshold = (
            isinstance(overall, (int, float)) and overall < quality_threshold
        )

        coordinator_requires = False
        if isinstance(coordinator_result, dict):
            coordinator_requires = not coordinator_result.get('approved', False)

        return needs_improvement or below_threshold or coordinator_requires

    def _aggregate_feedback(
        self,
        quality_result: Dict[str, Any],
        consistency_result: Dict[str, Any],
        coordinator_result: Dict[str, Any],
    ) -> List[str]:
        """품질/일관성/코디네이터 결과에서 피드백을 취합합니다."""

        feedback_items: List[str] = []

        if isinstance(quality_result, dict):
            feedback_items.extend(
                [f"[품질] {item}" for item in quality_result.get('feedback', []) if item]
            )

        if isinstance(consistency_result, dict):
            feedback_items.extend(
                [f"[일관성] {item}" for item in consistency_result.get('issues', []) if item]
            )

        if isinstance(coordinator_result, dict):
            feedback_items.extend(
                [
                    f"[코디네이터] {item}"
                    for item in coordinator_result.get('required_improvements', [])
                    if item
                ]
            )

        # 중복 제거 (순서 유지)
        seen = set()
        unique_feedback: List[str] = []
        for item in feedback_items:
            if item in seen:
                continue
            seen.add(item)
            unique_feedback.append(item)

        return unique_feedback

    def _apply_feedback_to_documents(
        self,
        documents: Dict[str, Dict[str, str]],
        feedback_items: List[str],
        service_type: ServiceType,
    ) -> List[str]:
        """피드백을 반영하여 문서를 갱신합니다."""

        if not feedback_items:
            return []

        updated_files: List[str] = []
        feedback_text = "\n".join(f"- {item}" for item in feedback_items)

        for agent_name in self._get_document_agent_order(service_type):
            if agent_name not in documents:
                continue

            agent = self.agents.get(agent_name)
            if not agent:
                continue

            current_content = documents[agent_name]['content']
            improvement_prompt = self._build_improvement_prompt(
                agent_name,
                current_content,
                feedback_text,
            )

            try:
                result = agent(improvement_prompt)
                processed = self._process_agent_result(agent_name, result)
                self._validate_and_record_template(agent_name, processed)
                save_result = self._save_agent_document_sync(agent_name, processed)
                if save_result:
                    updated_files.append(save_result['file_path'])
                    documents[agent_name]['content'] = processed
            except Exception:
                self._get_agent_logger(agent_name).exception(
                    "피드백 적용 실패"
                )

        return updated_files

    def _build_improvement_prompt(
        self,
        agent_name: str,
        current_content: str,
        feedback_text: str,
    ) -> str:
        """문서 개선을 위한 프롬프트를 생성합니다."""

        if agent_name == 'openapi':
            return (
                "You are updating an existing OpenAPI 3.1 specification based on review feedback.\n"
                "Return ONLY valid JSON for the entire specification. Do not wrap in code fences.\n\n"
                "Current specification:\n"
                f"{current_content}\n\n"
                "Feedback to address:\n"
                f"{feedback_text}"
            )

        title = f"{agent_name}.md"

        template_results = (
            self.context
            .get('documents', {})
            .get('template_results', {})
            .get(agent_name, {})
        )

        required_sections = template_results.get('required_sections') or []
        section_pairs: List[str] = []
        if required_sections:
            for idx in range(0, len(required_sections), 2):
                first = required_sections[idx]
                second = required_sections[idx + 1] if idx + 1 < len(required_sections) else first
                if second and second != first:
                    section_pairs.append(f"{first}/{second}")
                else:
                    section_pairs.append(first)

        section_guidance = ""
        if section_pairs:
            bullet_lines = "\n".join(f"- {heading}" for heading in section_pairs)
            section_guidance = (
                "모든 필수 섹션 헤더는 아래 목록의 텍스트를 정확히 유지해야 합니다."
                " (한글/영문 병기 포함).\n"
                f"{bullet_lines}\n\n"
            )

        return (
            f"당신은 {title} 문서를 개선하는 기술 문서 작성자입니다.\n"
            "아래 현재 문서를 검토하고 모든 피드백을 반영하여 전체 문서를 재작성하세요.\n"
            "문서 구조와 필수 섹션은 유지하되 내용을 구체화하고 명확하게 다듬으세요.\n"
            "결과는 완성된 한국어 문서 전체를 반환하세요.\n\n"
            f"{section_guidance}"
            "현재 문서:\n"
            "----\n"
            f"{current_content}\n"
            "----\n\n"
            "반영해야 할 피드백:\n"
            f"{feedback_text}"
        )

    def _get_document_agent_order(self, service_type: ServiceType) -> List[str]:
        """문서 생성/개선 순서를 반환합니다."""

        order = ['requirements', 'design', 'tasks', 'changes']
        if service_type == ServiceType.API:
            order.append('openapi')
        return order

    
    
    
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
        agent_logger = self._get_agent_logger(agent_name)

        try:
            if agent_name == 'openapi':
                template_result = validate_openapi_spec(
                    content,
                    **self._tool_kwargs(validate_openapi_spec),
                )
            else:
                template_result = apply_template(
                    content,
                    template_type,
                    **self._tool_kwargs(apply_template),
                )
        except Exception:
            agent_logger.exception("템플릿 검증 도구 호출 실패")
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

            agent_logger.error("템플릿 검증 실패 | 상세: %s", detail)
            raise ValueError(f"{agent_name} 템플릿 검증 실패: {detail}")

        return template_result


    async def _save_agent_document(self, agent_name: str, content: str) -> Optional[Dict[str, Any]]:
        """개별 에이전트 문서 즉시 저장 (비동기 버전)"""
        agent_logger = self._get_agent_logger(agent_name)
        try:
            output_dir = self.context['project']['output_dir']

            # 파일명 결정
            if agent_name == 'openapi':
                filename = 'openapi.json'
            else:
                filename = f'{agent_name}.md'
            
            # 파일 저장
            result = await write_spec_file(
                output_dir,
                content,
                filename,
                **self._tool_kwargs(write_spec_file),
            )

            if result.get("success"):
                file_info = {
                    "filename": filename,
                    "file_path": result.get("file_path"),
                    "size": result.get("size", 0)
                }
                # 저장된 파일 목록에 추가
                self.saved_files.append(result.get("file_path"))
                agent_logger.info(
                    "문서 저장 완료 | 파일: %s | 크기: %d bytes",
                    file_info["file_path"],
                    file_info["size"],
                )
                return file_info
            else:
                agent_logger.error(
                    "문서 저장 실패 | 파일: %s | 이유: %s",
                    filename,
                    result.get('error'),
                )
                return None

        except Exception:
            agent_logger.exception("문서 저장 중 오류 발생")
            return None
    
    def _save_agent_document_sync(self, agent_name: str, content: str) -> Optional[Dict[str, Any]]:
        """개별 에이전트 문서 즉시 저장 (동기 버전)"""
        agent_logger = self._get_agent_logger(agent_name)
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
            agent_logger.info(
                "문서 저장 완료 | 파일: %s | 작업: %s | 크기: %d bytes",
                str(file_path),
                action,
                file_size,
            )

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

        except Exception:
            agent_logger.exception("문서 저장 중 오류 발생")
            return None
    
    
    
    
    
    
    
    async def _collect_and_save_node_results(self, graph, service_type: ServiceType) -> List[str]:
        """Graph의 각 노드 결과를 수집하고 파일로 저장"""
        saved_files = []

        try:
            self.logger.info("Graph 노드 결과 수집 시작")
            # Graph 객체에서 노드별 결과 접근
            nodes_to_save = ['requirements', 'design', 'tasks', 'changes']
            if service_type == ServiceType.API:
                nodes_to_save.append('openapi')

            for node_name in nodes_to_save:
                try:
                    node_logger = self._get_agent_logger(node_name)
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
                            node_logger.info(
                                "문서 저장 완료 | 파일: %s | 작업: %s",
                                save_result['file_path'],
                                save_result['action'],
                            )
                        else:
                            node_logger.error("문서 저장 실패")
                    else:
                        node_logger.warning("노드 결과 없음")

                except Exception:
                    self._get_agent_logger(node_name).exception("노드 결과 처리 중 오류")

            self.logger.info("Graph 노드 결과 수집 완료 | 저장 파일 %d개", len(saved_files))
            return saved_files

        except Exception:
            self.logger.exception("노드 결과 수집 실패")
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
            
        except Exception:
            self._get_agent_logger(node_name).exception("노드 결과 접근 실패")
            return None
    
    async def _generate_remaining_documents(self, requirements_content: str, service_type: ServiceType) -> List[str]:
        """requirements.md를 기반으로 나머지 문서들 생성"""
        saved_files = []

        try:
            self.logger.info("나머지 문서 생성 시작")
            # 나머지 생성할 문서들
            remaining_agents = ['design', 'tasks', 'changes']
            if service_type == ServiceType.API:
                remaining_agents.append('openapi')

            current_content = {'requirements': requirements_content}

            for agent_name in remaining_agents:
                try:
                    agent_logger = self._get_agent_logger(agent_name)
                    agent_logger.info("문서 생성 시작")

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
                        agent_logger.info(
                            "문서 생성 완료 | 파일: %s | 작업: %s",
                            save_result['file_path'],
                            save_result['action'],
                        )
                    else:
                        agent_logger.error("문서 저장 실패")

                except Exception:
                    self._get_agent_logger(agent_name).exception("문서 생성 중 오류")
                    continue

            self.logger.info("나머지 문서 생성 완료 | 저장 파일 %d개", len(saved_files))
            return saved_files

        except Exception:
            self.logger.exception("나머지 문서 생성 실패")
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
        
        result = commit_changes(
            frs_id,
            service_type,
            files_written,
            **self._tool_kwargs(commit_changes),
        )

        if result.get("success"):
            self.logger.info(
                "Git 커밋 완료 | 해시: %s",
                result.get('commit_hash', '')[:8],
            )
        else:
            self.logger.warning("Git 커밋 실패 | 이유: %s", result.get('error'))
    
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