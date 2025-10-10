"""
Agentic Loop Orchestrator for multi-agent specification generation.

This orchestrator implements an iterative refinement approach with:
- Quality scoring and convergence criteria
- Cross-document validation and consistency checks
- Agent collaboration and feedback mechanisms
- Automatic refinement loops until quality thresholds are met
"""

import re
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
import time

from strands import Agent
from strands.models.openai import OpenAIModel

from .config import Config
from .models import ServiceType, GenerationContext, FRSDocument, ValidationResult
from .agents import (
    create_requirements_agent,
    create_design_agent,
    create_tasks_agent,
    create_changes_agent,
    create_openapi_agent,
    create_markdown_to_json_agent,
    create_validation_agent,
)
from .tools import (
    load_frs_document,
    create_output_directory,
    write_spec_file,
    create_git_branch,
    commit_changes,
)


class DocumentState(Enum):
    """문서 생성 상태."""

    DRAFT = "draft"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    FAILED = "failed"


class QualityScore:
    """상세 메트릭을 포함한 문서 품질 점수."""

    def __init__(self):
        self.completeness: float = 0.0  # 0-100
        self.consistency: float = 0.0  # 0-100
        self.clarity: float = 0.0  # 0-100
        self.technical_accuracy: float = 0.0  # 0-100
        self.overall: float = 0.0  # 0-100
        self.feedback: List[str] = []

    def calculate_overall(self):
        """가중치가 적용된 전체 점수 계산."""
        self.overall = (
            self.completeness * 0.3
            + self.consistency * 0.3
            + self.clarity * 0.2
            + self.technical_accuracy * 0.2
        )
        return self.overall

    def meets_threshold(self, threshold: float = 85.0) -> bool:
        """점수가 품질 임계값을 충족하는지 확인."""
        return self.overall >= threshold


class DocumentBundle:
    """문서 내용과 메타데이터를 담는 컨테이너."""

    def __init__(self, doc_type: str, content: str = ""):
        self.type = doc_type
        self.content = content
        self.state = DocumentState.DRAFT
        self.quality_score = QualityScore()
        self.iteration = 0
        self.feedback_history: List[str] = []

    def needs_refinement(self) -> bool:
        """문서가 개선이 필요한지 확인."""
        return (
            self.state == DocumentState.DRAFT
            and not self.quality_score.meets_threshold()
            and self.iteration < 3
        )


class AgenticOrchestrator:
    """
    반복적 개선을 통한 명세서 생성을 구현하는 Agentic Loop 오케스트레이터.

    주요 기능:
    - 품질 점수를 통한 반복적 문서 개선
    - 문서 간 검증 및 일관성 체크
    - 에이전트 협업 및 피드백 메커니즘
    - 품질 임계값 기반 수렴 기준
    """

    def __init__(self, config: Optional[Config] = None):
        """설정을 사용하여 Agentic 오케스트레이터 초기화."""
        self.config = config or Config.from_env()
        self.config.validate()

        # Quality thresholds (configurable)
        self.quality_threshold = getattr(config, "quality_threshold", 70.0)
        self.consistency_threshold = getattr(config, "consistency_threshold", 75.0)
        self.max_iterations = getattr(config, "max_iterations", 3)

        # Initialize specialized agents
        self.agents = self._initialize_agents()

        # Initialize coordinator agent for meta-operations
        self.coordinator = self._create_coordinator_agent()

        # Document bundles for tracking state
        self.documents: Dict[str, DocumentBundle] = {}

        # Performance tracking
        self.start_time = None
        self.last_save_times: Dict[str, float] = {}

    def _initialize_agents(self) -> Dict[str, Agent]:
        """모든 전문 에이전트 초기화."""
        return {
            "requirements": create_requirements_agent(self.config),
            "design": create_design_agent(self.config),
            "tasks": create_tasks_agent(self.config),
            "changes": create_changes_agent(self.config),
            "openapi": self._create_optimized_openapi_agent(),
            "md_to_json": self._create_optimized_json_agent(),
            "validation": create_validation_agent(self.config),
            "quality_scorer": self._create_quality_scorer_agent(),
            "consistency_checker": self._create_consistency_agent(),
        }

    def _create_coordinator_agent(self) -> Agent:
        """메타 코디네이터 에이전트 생성."""
        openai_model = OpenAIModel(
            model_id=self.config.openai_model,
            params={"temperature": 0.3},
            client_args={"api_key": self.config.openai_api_key},
        )

        return Agent(
            model=openai_model,
            tools=[
                load_frs_document,
                create_output_directory,
                write_spec_file,
                create_git_branch,
                commit_changes,
            ],
            system_prompt="""당신은 반복적 명세서 생성을 관리하는 Agentic 워크플로우 코디네이터입니다.
            
당신의 책임:
1. 피드백 루프를 통한 멀티 에이전트 협업 조율
2. 품질 점수 모니터링 및 개선 작업 트리거
3. 문서 간 일관성 보장
4. 품질 임계값까지 수렴 관리
5. 오류 및 폴백 우아하게 처리

반복적 개선을 통해 고품질의 일관된 명세서 달성에 집중하세요.""",
        )

    def _create_quality_scorer_agent(self) -> Agent:
        """품질 평가 에이전트 생성."""
        openai_model = OpenAIModel(
            model_id=self.config.openai_model,
            params={"temperature": 0.2, "max_tokens": 2000},
            client_args={"api_key": self.config.openai_api_key},
        )

        return Agent(
            model=openai_model,
            tools=[],
            system_prompt="""당신은 기술 명세서를 평가하는 문서 품질 분석가입니다.

다음 기준으로 문서를 평가하세요 (0-100 점수):
1. **완성도** (30%): 모든 필수 섹션이 존재하고 상세함
2. **일관성** (30%): 내부 일관성 및 다른 문서와의 정렬
3. **명확성** (20%): 명확하고 모호하지 않은 언어와 구조
4. **기술적 정확성** (20%): 올바른 기술적 세부사항과 실현 가능성

구조화된 평가 결과를 반환하세요:
- 각 기준별 점수
- 전체 가중 점수
- 개선을 위한 구체적 피드백
- 누락되거나 약한 섹션 목록

엄격하지만 공정하게 평가하세요. 85점 미만 문서는 개선이 필요합니다.""",
        )

    def _create_consistency_agent(self) -> Agent:
        """문서 간 일관성 검사 에이전트 생성."""
        openai_model = OpenAIModel(
            model_id=self.config.openai_model,
            params={"temperature": 0.2},
            client_args={"api_key": self.config.openai_api_key},
        )

        return Agent(
            model=openai_model,
            tools=[],
            system_prompt="""당신은 명세서 문서 간 정렬을 확인하는 일관성 검증자입니다.

검증 항목:
1. **요구사항 ↔ 설계**: 설계가 모든 요구사항을 충족
2. **설계 ↔ 작업**: 작업이 모든 설계 컴포넌트를 포함
3. **설계 ↔ 변경사항**: 변경사항이 설계 결정을 반영
4. **요구사항 ↔ OpenAPI**: API 스펙이 요구사항과 일치

식별 사항:
- 문서 간 누락된 참조
- 상충하는 정보
- 용어 불일치
- 범위 불일치

수정이 필요한 상세한 불일치 사항을 반환하세요.""",
        )

    def _create_optimized_openapi_agent(self) -> Agent:
        """토큰 제한이 있는 최적화된 OpenAPI 에이전트 생성."""
        openai_model = OpenAIModel(
            model_id=self.config.openai_model,
            params={
                "temperature": 0.1,
                "max_tokens": 3000,
            },  # Lower temp, higher tokens
            client_args={"api_key": self.config.openai_api_key},
        )

        return Agent(
            model=openai_model,
            tools=[],
            system_prompt="""당신은 간결한 OpenAPI 명세를 작성하는 API 문서화 전문가입니다.

중요: 토큰 제한을 피하기 위해 필수 엔드포인트만 생성하세요.

최소하지만 완전한 OpenAPI 3.1 명세를 마크다운 형식으로 생성:

1. **기본 정보**: 제목, 버전 (1.0.0), 설명
2. **핵심 엔드포인트만**: 최대 5개의 가장 중요한 엔드포인트
3. **필수 스키마**: 필요한 데이터 모델만
4. **표준 응답**: 200, 400, 401, 500

집중 사항:
- 인증 엔드포인트 (POST /auth/login)
- 메인 리소스 CRUD (GET, POST, PUT)
- 헬스 체크 (GET /health)

설명을 간결하게 유지하세요. 깊은 중첩을 피하세요. 깨끗하고 최소한의 문서를 생성하세요.""",
        )

    def _create_optimized_json_agent(self) -> Agent:
        """최적화된 JSON 변환 에이전트 생성."""
        openai_model = OpenAIModel(
            model_id=self.config.openai_model,
            params={
                "temperature": 0.05,
                "max_tokens": 4000,
            },  # Very low temp for precision
            client_args={"api_key": self.config.openai_api_key},
        )

        return Agent(
            model=openai_model,
            tools=[],
            system_prompt="""당신은 OpenAPI 명세를 위한 JSON 변환기입니다.

OpenAPI 마크다운을 유효한 JSON으로 변환하세요.

핵심 규칙:
1. 유효한 JSON만 생성 - 설명 없음
2. 구조를 최소화하고 평탄하게 유지
3. 필수 필드만으로 제한
4. 깊은 중첩 없이 단순한 스키마 사용
5. 최대 5개 엔드포인트

출력 형식: 순수 JSON만 (코드 블록 없음)

변환이 실패하거나 너무 클 경우, 최소한의 유효한 OpenAPI JSON 반환:
- info 섹션
- 하나의 health 엔드포인트
- 기본 200 응답""",
        )

    async def generate_specs_with_loop(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str] = None,
        use_git: bool = True,
    ) -> Dict[str, Any]:
        """
        반복적 개선을 사용하여 Agentic Loop로 명세서 생성.

        Args:
            frs_path: FRS 마크다운 파일 경로
            service_type: 서비스 유형 (API 또는 WEB)
            output_dir: 사용자 정의 출력 디렉토리
            use_git: git 워크플로우 사용 여부

        Returns:
            생성 결과와 품질 메트릭을 포함한 사전
        """
        try:
            self.start_time = time.time()
            print(f"🚀 Starting Optimized Agentic Loop specification generation...")
            print(f"📖 FRS: {frs_path}")
            print(f"🔧 Service Type: {service_type.value}")
            print(f"🎯 Quality Threshold: {self.quality_threshold}%")
            print(f"🔄 Max Iterations: {self.max_iterations}")
            if self.config.incremental_save:
                print(f"💾 Incremental save: Enabled")
            if self.config.early_stopping:
                print(
                    f"⏹️ Early stopping: Enabled (min improvement: {self.config.min_improvement_threshold}%)"
                )

            # Step 1: Initialize context
            context = await self._initialize_context(
                frs_path, service_type, output_dir, use_git
            )
            if not context:
                return {
                    "success": False,
                    "error": "Failed to initialize generation context",
                }

            # Step 2: Generate initial documents
            print("\n📝 Generating initial document drafts...")
            await self._generate_initial_drafts(context)

            # Step 3: Iterative refinement loop
            iteration = 0
            converged = False

            while iteration < self.max_iterations and not converged:
                iteration += 1
                print(f"\n🔄 Refinement Iteration {iteration}/{self.max_iterations}")

                # Store previous quality scores for improvement tracking
                previous_scores = {
                    doc_type: bundle.quality_score.overall
                    for doc_type, bundle in self.documents.items()
                }

                # Evaluate quality
                print("📊 Evaluating document quality...")
                quality_results = await self._evaluate_all_quality()

                # Check for meaningful improvements
                if self.config.early_stopping and iteration > 1:
                    should_continue = self._should_continue_iteration(
                        previous_scores, quality_results
                    )
                    if not should_continue:
                        print(
                            f"⏹️ Early stopping: Improvements below {self.config.min_improvement_threshold}% threshold"
                        )
                        break

                # Check consistency
                print("🔍 Checking cross-document consistency...")
                consistency_results = await self._check_consistency()

                # Check convergence
                converged = self._check_convergence(
                    quality_results, consistency_results
                )

                if converged:
                    print("✅ Quality thresholds met! Documents approved.")
                    break

                # Refine documents based on feedback
                print("♻️ Refining documents based on feedback...")
                await self._refine_documents(
                    quality_results, consistency_results, context
                )

            # Step 4: Final validation
            print("\n🏁 Running final validation...")
            final_validation = await self._final_validation()

            # Step 5: Write documents to disk
            print("\n💾 Writing approved documents...")
            files_written = await self._write_all_documents(context)

            # Step 6: Git operations
            if use_git and files_written:
                await self._commit_to_git(context, files_written)

            # Step 7: Generate summary report
            report = self._generate_summary_report(
                iteration, converged, quality_results
            )

            # Performance summary
            total_elapsed = time.time() - self.start_time
            print("\n🎉 Optimized Agentic Loop generation completed!")
            print(f"⏱️ Total Time: {total_elapsed:.1f}s")
            print(f"📊 Final Quality Score: {report['average_quality']:.1f}%")
            print(f"🔄 Iterations Used: {iteration}")
            print(f"📁 Files Generated: {len(files_written)}")

            # Show time per document if incremental save was used
            if self.config.incremental_save and self.last_save_times:
                print(f"💾 Incremental Saves Timeline:")
                for doc_type, save_time in self.last_save_times.items():
                    relative_time = save_time - self.start_time
                    print(f"    {doc_type}: {relative_time:.1f}s")

            return {
                "success": True,
                "output_dir": context.output_dir,
                "files_written": files_written,
                "quality_report": report,
                "iterations": iteration,
                "converged": converged,
                "total_time": total_elapsed,
                "incremental_saves": (
                    list(self.last_save_times.keys())
                    if self.config.incremental_save
                    else []
                ),
            }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)

            print(f"❌ Agentic orchestration failed ({error_type}): {error_msg}")

            # Provide specific guidance for token-related errors
            if (
                "max_tokens" in error_msg.lower()
                or "MaxTokensReachedException" in error_msg
            ):
                print(
                    "💡 Suggestion: Try reducing the input FRS size or use simpler requirements"
                )
                error_msg = f"Token limit exceeded ({error_type}). Try with shorter FRS content."

            return {
                "success": False,
                "error": f"Agentic orchestration failed: {error_msg}",
                "error_type": error_type,
            }

    async def _initialize_context(
        self,
        frs_path: str,
        service_type: ServiceType,
        output_dir: Optional[str],
        use_git: bool,
    ) -> Optional[GenerationContext]:
        """Initialize generation context and setup."""
        try:
            # Load FRS document
            from .tools import load_frs_document

            frs_result = load_frs_document(frs_path)

            if not frs_result.get("success", False):
                return None

            # Extract FRS information
            frs_content = frs_result.get("content", "")
            frs_id = self._extract_frs_id(frs_path)

            # Setup output directory
            output_dir_path = output_dir or f"specs/{frs_id}/{service_type.value}"
            from .tools import create_output_directory

            output_result = create_output_directory("specs", frs_id, service_type.value)

            if output_result.get("success"):
                output_dir_path = output_result.get("output_dir", output_dir_path)

            # Git setup
            if use_git:
                from .tools import create_git_branch

                git_result = create_git_branch(frs_id, service_type.value)
                if not git_result.get("success"):
                    print(f"⚠️ Git branch setup failed: {git_result.get('error')}")

            # Create context
            context = GenerationContext(
                frs=FRSDocument(title=f"FRS {frs_id}", content=frs_content),
                service_type=service_type,
                output_dir=output_dir_path,
            )

            return context

        except Exception as e:
            print(f"❌ Context initialization failed: {str(e)}")
            return None

    async def _generate_initial_drafts(self, context: GenerationContext):
        """Generate initial draft documents with incremental saving."""
        # Requirements generation
        print("  📋 Generating requirements draft...")
        req_bundle = DocumentBundle("requirements")

        try:
            # Truncate FRS content if too long (keep first 8000 chars for safety)
            frs_content = context.frs.content
            if len(frs_content) > 8000:
                print("  ⚠️ FRS content truncated to avoid token limits")
                frs_content = (
                    frs_content[:8000]
                    + "\n\n[... content truncated for processing ...]"
                )

            req_result = self.agents["requirements"](
                f"Generate requirements.md from FRS:\n\n{frs_content}\n\nService type: {context.service_type.value}"
            )
            req_bundle.content = self._clean_agent_response(str(req_result))
        except Exception as e:
            error_type = type(e).__name__
            print(f"  ⚠️ Requirements generation failed ({error_type}): {str(e)}")
            if "max_tokens" in str(e).lower() or "MaxTokensReachedException" in str(e):
                print("  🔧 Token limit hit, using simplified template")
            # Fallback to template-based generation
            req_bundle.content = self._generate_fallback_requirements(context)

        self.documents["requirements"] = req_bundle
        context.requirements = req_bundle.content

        # Incremental save for requirements
        if self.config.incremental_save:
            await self._save_document_immediately(context, "requirements", req_bundle)

        # Design generation (depends on requirements)
        print("  🏗️ Generating design draft...")
        design_bundle = DocumentBundle("design")

        try:
            # Truncate requirements if too long
            req_content = (
                context.requirements[:6000]
                if len(context.requirements) > 6000
                else context.requirements
            )

            design_result = self.agents["design"](
                f"Generate design.md from requirements:\n\n{req_content}\n\nService type: {context.service_type.value}"
            )
            design_bundle.content = self._clean_agent_response(str(design_result))
        except Exception as e:
            error_type = type(e).__name__
            print(f"  ⚠️ Design generation failed ({error_type}): {str(e)}")
            if "max_tokens" in str(e).lower() or "MaxTokensReachedException" in str(e):
                print("  🔧 Token limit hit, using simplified template")
            design_bundle.content = self._generate_fallback_design(context)

        self.documents["design"] = design_bundle
        context.design = design_bundle.content

        # Incremental save for design
        if self.config.incremental_save:
            await self._save_document_immediately(context, "design", design_bundle)

        # Tasks generation (depends on design)
        print("  📝 Generating tasks draft...")
        tasks_bundle = DocumentBundle("tasks")

        try:
            # Truncate design if too long
            design_content = (
                context.design[:5000] if len(context.design) > 5000 else context.design
            )

            tasks_result = self.agents["tasks"](
                f"Generate tasks.md from design:\n\n{design_content}"
            )
            tasks_bundle.content = self._clean_agent_response(str(tasks_result))
        except Exception as e:
            error_type = type(e).__name__
            print(f"  ⚠️ Tasks generation failed ({error_type}): {str(e)}")
            if "max_tokens" in str(e).lower() or "MaxTokensReachedException" in str(e):
                print("  🔧 Token limit hit, using simplified template")
            tasks_bundle.content = self._generate_fallback_tasks(context)

        self.documents["tasks"] = tasks_bundle
        context.tasks = tasks_bundle.content

        # Incremental save for tasks
        if self.config.incremental_save:
            await self._save_document_immediately(context, "tasks", tasks_bundle)

        # Changes generation (depends on requirements and design)
        print("  📄 Generating changes draft...")
        changes_bundle = DocumentBundle("changes")

        try:
            # Truncate content to avoid token limits
            req_summary = (
                context.requirements[:3000]
                if len(context.requirements) > 3000
                else context.requirements
            )
            design_summary = (
                context.design[:3000] if len(context.design) > 3000 else context.design
            )

            changes_result = self.agents["changes"](
                f"Generate changes.md from requirements and design:\n\nRequirements (summary):\n{req_summary}\n\nDesign (summary):\n{design_summary}"
            )
            changes_bundle.content = self._clean_agent_response(str(changes_result))
        except Exception as e:
            error_type = type(e).__name__
            print(f"  ⚠️ Changes generation failed ({error_type}): {str(e)}")
            if "max_tokens" in str(e).lower() or "MaxTokensReachedException" in str(e):
                print("  🔧 Token limit hit, using simplified template")
            changes_bundle.content = self._generate_fallback_changes(context)

        self.documents["changes"] = changes_bundle
        context.changes = changes_bundle.content

        # Incremental save for changes
        if self.config.incremental_save:
            await self._save_document_immediately(context, "changes", changes_bundle)

        # OpenAPI generation for API services with enhanced error handling
        if context.service_type == ServiceType.API:
            print("  🔌 Generating OpenAPI draft...")
            openapi_bundle = DocumentBundle("openapi")

            try:
                # Extract key API information more selectively
                req_api_info = self._extract_api_essentials(context.requirements)
                design_api_info = self._extract_api_essentials(context.design)

                # Create focused prompt for minimal OpenAPI
                openapi_prompt = f"""Generate minimal OpenAPI 3.1 specification for:
                
Service: {context.frs.title}
Type: API Service

Key Requirements:
{req_api_info}

Key Design Elements:
{design_api_info}

Generate ONLY essential endpoints (max 5). Keep it concise."""

                openapi_result = self.agents["openapi"](openapi_prompt)
                openapi_bundle.content = self._clean_agent_response(str(openapi_result))

            except Exception as e:
                print(f"  ⚠️ OpenAPI generation failed ({type(e).__name__}): {str(e)}")
                if "max_tokens" in str(e).lower() or "MaxTokensReachedException" in str(
                    e
                ):
                    print("  🔧 Token limit detected, using ultra-minimal template")
                    openapi_bundle.content = self._generate_minimal_openapi(context)
                else:
                    openapi_bundle.content = self._generate_fallback_openapi(context)

            self.documents["openapi"] = openapi_bundle
            context.openapi = openapi_bundle.content

            # Incremental save for OpenAPI
            if self.config.incremental_save:
                await self._save_document_immediately(
                    context, "openapi", openapi_bundle
                )

    async def _evaluate_all_quality(self) -> Dict[str, QualityScore]:
        """Evaluate quality of all documents with parallel processing option."""
        quality_results = {}

        if self.config.parallel_processing:
            # Parallel quality evaluation
            tasks = []
            doc_items = []

            for doc_type, bundle in self.documents.items():
                if bundle.state == DocumentState.APPROVED:
                    continue
                doc_items.append((doc_type, bundle))
                tasks.append(self._evaluate_single_document_quality(doc_type, bundle))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        print(
                            f"    ⚠️ Quality evaluation failed for {doc_items[i][0]}: {result}"
                        )
                        continue

                    doc_type, score = result
                    bundle = doc_items[i][1]
                    bundle.quality_score = score
                    quality_results[doc_type] = score

                    # Update state based on score
                    if score.meets_threshold(self.quality_threshold):
                        bundle.state = DocumentState.REVIEWING
        else:
            # Sequential quality evaluation (original behavior)
            for doc_type, bundle in self.documents.items():
                if bundle.state == DocumentState.APPROVED:
                    continue

                score = await self._evaluate_single_document_quality(doc_type, bundle)
                if isinstance(score, tuple):
                    _, score = score

                bundle.quality_score = score
                quality_results[doc_type] = score

                # Update state based on score
                if score.meets_threshold(self.quality_threshold):
                    bundle.state = DocumentState.REVIEWING

        return quality_results

    async def _evaluate_single_document_quality(
        self, doc_type: str, bundle: DocumentBundle
    ) -> tuple:
        """Evaluate quality of a single document."""
        try:
            # Truncate content if too long for quality evaluation
            content = (
                bundle.content[:4000] if len(bundle.content) > 4000 else bundle.content
            )

            score_prompt = f"""Evaluate the quality of this {doc_type} document:

{content}

Provide scores (0-100) for:
1. Completeness
2. Consistency  
3. Clarity
4. Technical Accuracy

Also provide specific feedback for improvements."""

            result = self.agents["quality_scorer"](score_prompt)

            # Parse scores from result
            score = self._parse_quality_score(str(result))
            print(
                f"    📊 {doc_type}: {score.overall:.1f}% (C:{score.completeness:.0f} S:{score.consistency:.0f} L:{score.clarity:.0f} T:{score.technical_accuracy:.0f})"
            )

            return (doc_type, score)
        except Exception as e:
            print(f"    ⚠️ Quality evaluation failed for {doc_type}: {str(e)}")
            # Return default score on failure
            default_score = QualityScore()
            default_score.overall = 50.0
            return (doc_type, default_score)

    async def _check_consistency(self) -> Dict[str, List[str]]:
        """Check cross-document consistency."""
        consistency_issues = {}

        # Check requirements vs design
        if "requirements" in self.documents and "design" in self.documents:
            check_prompt = f"""Check consistency between requirements and design:

Requirements:
{self.documents['requirements'].content}

Design:
{self.documents['design'].content}

List any inconsistencies or missing alignments."""

            result = self.agents["consistency_checker"](check_prompt)
            issues = self._parse_consistency_issues(str(result))
            if issues:
                consistency_issues["requirements-design"] = issues

        # Check design vs tasks
        if "design" in self.documents and "tasks" in self.documents:
            check_prompt = f"""Check consistency between design and tasks:

Design:
{self.documents['design'].content}

Tasks:
{self.documents['tasks'].content}

List any missing tasks or misalignments."""

            result = self.agents["consistency_checker"](check_prompt)
            issues = self._parse_consistency_issues(str(result))
            if issues:
                consistency_issues["design-tasks"] = issues

        return consistency_issues

    def _check_convergence(
        self,
        quality_results: Dict[str, QualityScore],
        consistency_results: Dict[str, List[str]],
    ) -> bool:
        """Check if documents have converged to quality thresholds."""
        # Check quality scores
        all_quality_met = all(
            score.meets_threshold(self.quality_threshold)
            for score in quality_results.values()
        )

        # Check consistency
        no_major_issues = len(consistency_results) == 0

        # Mark approved documents
        if all_quality_met and no_major_issues:
            for bundle in self.documents.values():
                if bundle.state == DocumentState.REVIEWING:
                    bundle.state = DocumentState.APPROVED

        return all_quality_met and no_major_issues

    async def _refine_documents(
        self,
        quality_results: Dict[str, QualityScore],
        consistency_results: Dict[str, List[str]],
        context: GenerationContext,
    ):
        """Refine documents based on quality and consistency feedback."""
        for doc_type, bundle in self.documents.items():
            if bundle.state == DocumentState.APPROVED:
                continue

            if not bundle.needs_refinement():
                continue

            # Compile feedback
            feedback = []

            # Add quality feedback
            if doc_type in quality_results:
                score = quality_results[doc_type]
                if score.feedback:
                    feedback.extend(score.feedback)

            # Add consistency feedback
            for issue_key, issues in consistency_results.items():
                if doc_type in issue_key:
                    feedback.extend(issues)

            if not feedback:
                continue

            # Refine document with feedback
            refine_prompt = f"""Refine this {doc_type} document based on the following feedback:

Current document:
{bundle.content}

Feedback to address:
{chr(10).join(f'- {f}' for f in feedback)}

Generate an improved version that addresses all feedback while maintaining the document structure and requirements."""

            # Use appropriate agent for refinement
            agent_name = doc_type if doc_type in self.agents else "requirements"
            result = self.agents[agent_name](refine_prompt)

            # Update bundle
            bundle.content = self._clean_agent_response(str(result))
            bundle.iteration += 1
            bundle.feedback_history.extend(feedback)
            bundle.state = DocumentState.DRAFT

            # Incremental save after refinement
            if self.config.incremental_save:
                await self._save_document_immediately(context, doc_type, bundle)

    async def _final_validation(self) -> ValidationResult:
        """Run final validation on all documents."""
        all_valid = True
        errors = []
        warnings = []

        for doc_type, bundle in self.documents.items():
            if bundle.state != DocumentState.APPROVED:
                warnings.append(
                    f"{doc_type} not fully approved (state: {bundle.state.value})"
                )
                all_valid = False

            # Run validation agent
            validation_result = self.agents["validation"](
                f"Validate {doc_type} document:\n\n{bundle.content}"
            )

            # Parse validation results
            if "error" in str(validation_result).lower():
                errors.append(f"{doc_type}: {validation_result}")
                all_valid = False

        return ValidationResult(
            success=all_valid,
            errors=errors,
            warnings=warnings,
            summary=f"Final validation: {'PASSED' if all_valid else 'FAILED'}",
        )

    async def _write_all_documents(self, context: GenerationContext) -> List[str]:
        """Write all approved documents to disk."""
        files_written = []

        for doc_type, bundle in self.documents.items():
            # Write document even if not fully approved (with warning)
            if bundle.state != DocumentState.APPROVED:
                print(
                    f"  ⚠️ Writing {doc_type} (quality: {bundle.quality_score.overall:.1f}%, state: {bundle.state.value})"
                )
            else:
                print(f"  ✅ Writing {doc_type} (approved)")

            # Skip only if document is empty or failed
            if not bundle.content or bundle.state == DocumentState.FAILED:
                print(f"  ❌ Skipping {doc_type} (no content)")
                continue

            # Determine filename
            filename = f"{doc_type}.md"
            if doc_type == "openapi":
                # Convert to JSON for OpenAPI
                json_result = self.agents["md_to_json"](bundle.content)
                json_content = self._clean_json_response(str(json_result))

                # Validate JSON
                try:
                    json.loads(json_content)
                    filename = "apis.json"
                    content = json_content
                except json.JSONDecodeError:
                    print(f"  ⚠️ Failed to convert OpenAPI to JSON, keeping markdown")
                    content = bundle.content
            else:
                content = bundle.content

            # Write file
            file_path = self._write_document(context.output_dir, filename, content)
            if file_path:
                files_written.append(file_path)
                print(f"  ✅ Written: {filename}")

        return files_written

    async def _commit_to_git(
        self, context: GenerationContext, files_written: List[str]
    ):
        """Commit generated files to git."""
        print("\n💾 Committing to git...")
        frs_id = self._extract_frs_id(context.frs.title)

        from .tools import commit_changes

        commit_result = commit_changes(
            f"spec({frs_id}): add {context.service_type.value} specs via Agentic Loop",
            files_written,
        )

        if commit_result.get("success"):
            print("✅ Changes committed successfully")
        else:
            print(f"⚠️ Commit failed: {commit_result.get('error')}")

    def _generate_summary_report(
        self, iterations: int, converged: bool, quality_results: Dict[str, QualityScore]
    ) -> Dict[str, Any]:
        """Generate summary report of the generation process."""
        # Calculate average quality
        avg_quality = 0.0
        if quality_results:
            avg_quality = sum(s.overall for s in quality_results.values()) / len(
                quality_results
            )

        # Document states
        doc_states = {
            doc_type: bundle.state.value for doc_type, bundle in self.documents.items()
        }

        # Quality breakdown
        quality_breakdown = {
            doc_type: {
                "overall": score.overall,
                "completeness": score.completeness,
                "consistency": score.consistency,
                "clarity": score.clarity,
                "technical_accuracy": score.technical_accuracy,
            }
            for doc_type, score in quality_results.items()
        }

        return {
            "iterations": iterations,
            "converged": converged,
            "average_quality": avg_quality,
            "document_states": doc_states,
            "quality_breakdown": quality_breakdown,
            "timestamp": datetime.now().isoformat(),
        }

    # Utility methods

    def _extract_frs_id(self, frs_path: str) -> str:
        """Extract FRS ID from file path."""
        path = Path(frs_path)
        match = re.search(r"FRS-(\d+)", str(path))
        return f"FRS-{match.group(1)}" if match else path.stem

    def _write_document(
        self, output_dir: str, filename: str, content: str
    ) -> Optional[str]:
        """Write document content to file."""
        try:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)

            file_path = output_path / filename
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return str(file_path)
        except Exception as e:
            print(f"❌ Failed to write {filename}: {str(e)}")
            return None

    def _clean_agent_response(self, response: str) -> str:
        """Clean agent response by removing wrappers."""
        if not response:
            return ""

        # Remove markdown code blocks
        response = re.sub(
            r"```(?:markdown|md)?\n(.*?)\n```", r"\1", response, flags=re.DOTALL
        )

        # Remove leading explanations
        lines = response.split("\n")
        for i, line in enumerate(lines):
            if line.startswith("#"):
                return "\n".join(lines[i:])

        return response.strip()

    def _clean_json_response(self, response: str) -> str:
        """Clean JSON response from agent."""
        # Remove code blocks
        if "```json" in response:
            match = re.search(r"```json\s*\n(.*?)\n```", response, re.DOTALL)
            if match:
                return match.group(1).strip()

        # Find JSON object
        json_start = response.find("{")
        if json_start != -1:
            json_end = response.rfind("}")
            if json_end > json_start:
                return response[json_start : json_end + 1]

        return response.strip()

    async def _save_document_immediately(
        self, context: GenerationContext, doc_type: str, bundle: DocumentBundle
    ):
        """Save document immediately to disk with progress feedback."""
        try:
            # Determine filename
            filename = f"{doc_type}.md"
            content = bundle.content

            # Handle OpenAPI special case with enhanced error handling
            if doc_type == "openapi" and bundle.content:
                try:
                    # Check content size before conversion
                    if len(bundle.content) > 8000:
                        print(
                            f"    ⚠️ OpenAPI content too large ({len(bundle.content)} chars), keeping as markdown"
                        )
                    else:
                        # Try to convert to JSON with minimal prompt
                        json_prompt = f"Convert to JSON:\n\n{bundle.content[:4000]}"
                        json_result = self.agents["md_to_json"](json_prompt)
                        json_content = self._clean_json_response(str(json_result))

                        # Validate JSON
                        import json

                        parsed = json.loads(json_content)

                        # Ensure it's not too large
                        if len(json_content) < 15000:  # 15KB limit
                            filename = "apis.json"
                            content = json_content
                            print(
                                f"    ✅ Successfully converted to JSON ({len(json_content)} chars)"
                            )
                        else:
                            print(
                                f"    ⚠️ JSON too large ({len(json_content)} chars), keeping as markdown"
                            )

                except Exception as e:
                    print(
                        f"    ⚠️ JSON conversion failed ({type(e).__name__}): keeping as markdown"
                    )
                    # Keep as markdown if JSON conversion fails

            # Write file
            file_path = self._write_document(context.output_dir, filename, content)
            if file_path:
                elapsed = time.time() - self.start_time
                self.last_save_times[doc_type] = time.time()
                print(
                    f"    💾 Saved {filename} (quality: {bundle.quality_score.overall:.1f}%, elapsed: {elapsed:.1f}s)"
                )
                return file_path
        except Exception as e:
            print(f"    ⚠️ Failed to save {doc_type}: {str(e)}")
        return None

    def _should_continue_iteration(
        self,
        previous_scores: Dict[str, float],
        current_results: Dict[str, QualityScore],
    ) -> bool:
        """Check if iteration should continue based on improvement threshold."""
        meaningful_improvements = 0
        total_docs = len(current_results)

        for doc_type, current_score in current_results.items():
            previous_score = previous_scores.get(doc_type, 0.0)
            improvement = current_score.overall - previous_score

            if improvement >= self.config.min_improvement_threshold:
                meaningful_improvements += 1
                print(
                    f"    📈 {doc_type}: {previous_score:.1f}% → {current_score.overall:.1f}% (+{improvement:.1f}%)"
                )
            else:
                print(
                    f"    📊 {doc_type}: {previous_score:.1f}% → {current_score.overall:.1f}% (+{improvement:.1f}%)"
                )

        # Continue if at least 50% of documents show meaningful improvement
        should_continue = meaningful_improvements >= (total_docs * 0.5)
        print(
            f"    🎯 Meaningful improvements: {meaningful_improvements}/{total_docs} (threshold: {self.config.min_improvement_threshold}%)"
        )

        return should_continue

    def _extract_api_essentials(self, content: str) -> str:
        """Extract essential API information from content, keeping it concise."""
        if not content:
            return "No specific information available"

        # Extract only lines mentioning API, endpoints, authentication, or data
        essential_lines = []
        lines = content.split("\n")

        keywords = [
            "api",
            "endpoint",
            "auth",
            "login",
            "user",
            "data",
            "response",
            "request",
            "get",
            "post",
            "put",
            "delete",
        ]

        for line in lines[:50]:  # Only check first 50 lines
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in keywords):
                essential_lines.append(line.strip())
                if len(essential_lines) >= 10:  # Limit to 10 most relevant lines
                    break

        result = "\n".join(essential_lines)
        return (
            result[:800]
            if result
            else "Core API functionality with standard CRUD operations"
        )

    def _generate_minimal_openapi(self, context: GenerationContext) -> str:
        """토큰 제한에 달했을 때 최소한의 OpenAPI 생성."""
        from datetime import datetime

        service_name = context.frs.title.replace("FRS ", "").replace("-", " ")

        return f"""# {service_name} API

## API 정보
- **제목**: {service_name} API
- **버전**: 1.0.0
- **설명**: 최소한 API 명세

## 인증
- **유형**: Bearer 토큰
- **헤더**: Authorization: Bearer <token>

## 핵심 엔드포인트

### 헬스 체크
- **GET** `/health`
- **설명**: API 상태 확인
- **응답**: 200 OK

### 인증
- **POST** `/auth/login`
- **설명**: 사용자 로그인
- **요청**: {{"email": "string", "password": "string"}}
- **응답**: 200 OK with token

### 메인 리소스
- **GET** `/api/v1/items`
- **설명**: 아이템 목록 조회
- **응답**: 200 OK with array

- **POST** `/api/v1/items`
- **설명**: 아이템 생성
- **요청**: {{"name": "string", "data": "object"}}
- **응답**: 201 Created

생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    def _generate_fallback_openapi(self, context: GenerationContext) -> str:
        """폴백 OpenAPI 문서 생성."""
        from datetime import datetime

        return f"""# OpenAPI 문서

## API 정보
- 제목: {context.frs.title} API
- 버전: 1.0.0
- 서비스 유형: {context.service_type.value}

## 기본 URL
- 개발: http://localhost:3000/api/v1
- 운영: https://api.example.com/v1

## 인증
- 유형: Bearer 토큰 (JWT)
- 헤더: Authorization: Bearer <token>

## 공통 엔드포인트

### 헬스 체크
- **GET** `/health`
- 설명: 서비스 상태 확인
- 응답: 200 OK

### 인증
- **POST** `/auth/login`
- 설명: 사용자 인증
- 요청 바디: {{"email": "string", "password": "string"}}
- 응답: 200 OK with JWT token

### 사용자 관리
- **GET** `/users/profile`
- 설명: 사용자 프로필 조회
- 헤더: 인증 필수
- 응답: 200 OK with user data

생성 대상: {context.frs.title}
분석 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

    def _generate_fallback_requirements(self, context: GenerationContext) -> str:
        """폴백 요구사항 문서 생성."""
        from datetime import datetime

        return f"""# 요구사항 문서

## 헤더/메타
- 문서: {context.frs.title} 요구사항
- 서비스 유형: {context.service_type.value}
- 생성일: {datetime.now().isoformat()}

## 범위
- 서비스 경계 및 인터페이스
- 핵심 기능 구현

## 기능 요구사항
- REQ-001: 핵심 서비스 기능 구현
- REQ-002: 사용자 인증 및 권한 부여
- REQ-003: 데이터 검증 및 처리

## 오류 요구사항
- ERR-001: 잘못된 입력을 우아하게 처리
- ERR-002: 디버깅을 위해 모든 오류 로깅
- ERR-003: 의미 있는 오류 메시지 제공

## 보안 & 개인정보
- SEC-001: 보안 인증
- SEC-002: 저장 및 전송 시 데이터 암호화
- SEC-003: GDPR 준수

## 관측 가능성
- OBS-001: 헬스 체크 엔드포인트
- OBS-002: 성능 메트릭
- OBS-003: 오류 추적

## 수용 기준
- 모든 요구사항이 구현되고 테스트됨
- 보안 조치가 제자리에 있음
- 성능 목표가 달성됨
"""

    def _generate_fallback_design(self, context: GenerationContext) -> str:
        """폴백 설계 문서 생성."""
        from datetime import datetime

        return f"""# 설계 문서

## 아키텍처
- 서비스 지향 아키텍처
- RESTful API 설계
- 데이터베이스 지속성 계층

## 시퀀스 다이어그램
```mermaid
sequenceDiagram
    클라이언트->>서비스: 요청
    서비스->>데이터베이스: 쿼리
    데이터베이스-->>서비스: 응답
    서비스-->>클라이언트: 결과
```

## 데이터 모델
- 사용자 엔티티
- 세션 관리
- 감사 로깅

## API 계약
- 표준 REST 엔드포인트
- JSON 요청/응답 형식
- HTTP 상태 코드

## 보안 & 권한
- JWT 인증
- 역할 기반 접근 제어
- API 요청 빈도 제한

## 성능 목표
- 응답 시간 < 200ms
- 99.9% 가용성
- 수평 확장성
"""

    def _generate_fallback_tasks(self, context: GenerationContext) -> str:
        """폴백 작업 문서 생성."""
        from datetime import datetime

        return f"""작업 문서

## 에픽
| 에픽 ID | 제목 | 설명 |
|---------|-------|-------------|
| E-001   | 서비스 구현 | 핵심 서비스 개발 |

## 스토리
| 스토리 ID | 에픽 ID | 제목 | 우선순위 |
|----------|---------|-------|----------|
| S-001    | E-001   | 핵심 API | 높음 |
| S-002    | E-001   | 보안 | 높음 |

## 태스크
| 태스크 ID | 스토리 ID | 제목 | 예상시간 |
|---------|----------|-------|----------|
| T-001   | S-001    | 설정 | 4h |
| T-002   | S-001    | 구현 | 16h |

## DoD (완료 정의)
- [ ] 코드 완성
- [ ] 테스트 통과
- [ ] 코드 리뷰 완료
- [ ] 문서화 완료
"""

    def _generate_fallback_changes(self, context: GenerationContext) -> str:
        """폴백 변경사항 문서 생성."""
        from datetime import datetime

        return f"""변경사항 문서

## 버전 이력
| 버전 | 날짜 | 변경사항 |
|---------|------|---------|
| 1.0.0   | {datetime.now().strftime('%Y-%m-%d')} | 초기 릴리스 |

## 변경 요약
- 새로운 서비스 구현
- 핵심 기능 배포

## 영향/위험
- 영향: 새로운 서비스
- 위험: 보통
- 완화: 테스트 및 모니터링

## 롤백 계획
1. 서비스 중단
2. 배포 롤백
3. 시스템 상태 확인

## 알려진 문제
- 초기 배포
- 성능 모니터링
"""

    def _parse_quality_score(self, result: str) -> QualityScore:
        """에이전트 결과에서 품질 점수 파싱."""
        score = QualityScore()

        # Simple pattern matching for scores
        patterns = {
            "completeness": r"completeness[:\s]+(\d+)",
            "consistency": r"consistency[:\s]+(\d+)",
            "clarity": r"clarity[:\s]+(\d+)",
            "technical_accuracy": r"technical[:\s]+accuracy[:\s]+(\d+)",
        }

        for attr, pattern in patterns.items():
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                setattr(score, attr, float(match.group(1)))

        # Extract feedback
        feedback_match = re.search(
            r"feedback:(.*?)(?:$|\n\n)", result, re.DOTALL | re.IGNORECASE
        )
        if feedback_match:
            feedback_text = feedback_match.group(1).strip()
            score.feedback = [f.strip() for f in feedback_text.split("\n") if f.strip()]

        score.calculate_overall()
        return score

    def _parse_consistency_issues(self, result: str) -> List[str]:
        """에이전트 결과에서 일관성 문제 파싱."""
        issues = []

        # Look for bullet points or numbered lists
        lines = result.split("\n")
        for line in lines:
            line = line.strip()
            if line and (
                line.startswith("-")
                or line.startswith("*")
                or re.match(r"^\d+\.", line)
            ):
                # Remove list markers
                issue = re.sub(r"^[-*\d.]+\s*", "", line)
                if issue:
                    issues.append(issue)

        return issues


# Convenience function for synchronous usage
def generate_specs_agentic(
    frs_path: str,
    service_type: ServiceType,
    output_dir: Optional[str] = None,
    config: Optional[Config] = None,
) -> Dict[str, Any]:
    """
    Synchronous wrapper for Agentic Loop specification generation.

    Args:
        frs_path: Path to FRS markdown file
        service_type: Type of service (API or WEB)
        output_dir: Custom output directory
        config: Configuration object

    Returns:
        Generation results with quality metrics
    """
    orchestrator = AgenticOrchestrator(config)

    # Run async method in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            orchestrator.generate_specs_with_loop(
                frs_path=frs_path, service_type=service_type, output_dir=output_dir
            )
        )
        return result
    finally:
        loop.close()
