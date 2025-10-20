from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from spec_agent.models import ServiceType

from ..context import WorkflowContext
from ..prompts import (
    build_changes_prompt,
    build_design_prompt,
    build_openapi_prompt,
    build_requirements_prompt,
    build_tasks_prompt,
)

AgentCallable = Callable[[Any], Any]
AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
ProcessResultFn = Callable[[str, Any], str]
ValidateTemplateFn = Callable[[str, str], Dict[str, Any]]
SaveDocumentFn = Callable[[str, str], Optional[Dict[str, Any]]]


class DocumentGenerationPhase:
    """요구사항·설계·작업 등 문서를 순차적으로 생성합니다."""

    def __init__(
        self,
        context: WorkflowContext,
        agents: Dict[str, AgentCallable],
        logger: logging.LoggerAdapter,
        agent_logger_factory: AgentLoggerFactory,
        process_agent_result: ProcessResultFn,
        validate_and_record: ValidateTemplateFn,
        save_document: SaveDocumentFn,
    ) -> None:
        self.context = context
        self.agents = agents
        self.logger = logger
        self.agent_logger_factory = agent_logger_factory
        self.process_agent_result = process_agent_result
        self.validate_and_record = validate_and_record
        self.save_document = save_document

    async def execute(self, service_type: ServiceType) -> Dict[str, Any]:
        """문서를 순차적으로 생성합니다."""

        self.logger.info("문서 생성 단계 시작")

        try:
            saved_files: List[str] = []
            output_dir = str(Path(self.context.project.get("output_dir", "")).resolve())

            frs_path = Path(self.context.project.get("frs_path", ""))
            previous_results = self.context.quality.get("previous_results")

            saved_files.extend(
                self._generate_requirements(frs_path, service_type, previous_results)
            )
            saved_files.extend(
                self._generate_design(output_dir, service_type, previous_results)
            )
            saved_files.extend(
                self._generate_tasks(output_dir, previous_results)
            )
            saved_files.extend(
                self._generate_changes(output_dir, service_type, previous_results)
            )

            if service_type == ServiceType.API:
                saved_files.extend(
                    self._generate_openapi(output_dir, previous_results)
                )

            unique_files = list(dict.fromkeys(saved_files))
            self.logger.info(
                "문서 생성 단계 종료 | 저장 파일 %d개", len(unique_files)
            )
            return {
                "success": True,
                "saved_files": unique_files,
                "execution_type": "document_generation",
            }

        except Exception as exc:
            self.logger.exception("문서 생성 단계 실패")
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # 개별 문서 생성 헬퍼
    # ------------------------------------------------------------------ #

    def _generate_requirements(
        self,
        frs_path: Path,
        service_type: ServiceType,
        previous_results: Optional[Dict[str, Any]],
    ) -> List[str]:
        logger = self.agent_logger_factory("requirements")
        logger.info("requirements 문서 생성 시작")

        prompt = build_requirements_prompt(
            frs_path,
            service_type.value,
            previous_results=previous_results,
        )
        result = self.agents["requirements"](prompt)
        content = self.process_agent_result("requirements", result)
        self.validate_and_record("requirements", content)
        save_result = self.save_document("requirements", content)

        if save_result:
            logger.info("requirements 저장 완료 | 파일: %s", save_result["file_path"])
            self.context.documents.previous_contents["requirements"] = content
            return [save_result["file_path"]]

        logger.warning("requirements 저장 실패")
        return []

    def _generate_design(
        self,
        output_dir: str,
        service_type: ServiceType,
        previous_results: Optional[Dict[str, Any]],
    ) -> List[str]:
        logger = self.agent_logger_factory("design")
        logger.info("design 문서 생성 시작")

        prompt = build_design_prompt(
            output_dir,
            service_type.value,
            previous_results=previous_results,
        )
        result = self.agents["design"](prompt)
        content = self.process_agent_result("design", result)
        self.validate_and_record("design", content)
        save_result = self.save_document("design", content)

        if save_result:
            logger.info("design 저장 완료 | 파일: %s", save_result["file_path"])
            self.context.documents.previous_contents["design"] = content
            return [save_result["file_path"]]

        logger.warning("design 저장 실패")
        return []

    def _generate_tasks(
        self,
        output_dir: str,
        previous_results: Optional[Dict[str, Any]],
    ) -> List[str]:
        logger = self.agent_logger_factory("tasks")
        logger.info("tasks 문서 생성 시작")

        prompt = build_tasks_prompt(
            output_dir,
            previous_results=previous_results,
        )
        result = self.agents["tasks"](prompt)
        content = self.process_agent_result("tasks", result)
        self.validate_and_record("tasks", content)
        save_result = self.save_document("tasks", content)

        if save_result:
            logger.info("tasks 저장 완료 | 파일: %s", save_result["file_path"])
            self.context.documents.previous_contents["tasks"] = content
            return [save_result["file_path"]]

        logger.warning("tasks 저장 실패")
        return []

    def _generate_changes(
        self,
        output_dir: str,
        service_type: ServiceType,
        previous_results: Optional[Dict[str, Any]],
    ) -> List[str]:
        logger = self.agent_logger_factory("changes")
        logger.info("changes 문서 생성 시작")

        prompt = build_changes_prompt(
            output_dir,
            service_type.value,
            previous_results=previous_results,
        )
        result = self.agents["changes"](prompt)
        content = self.process_agent_result("changes", result)
        self.validate_and_record("changes", content)
        save_result = self.save_document("changes", content)

        if save_result:
            logger.info("changes 저장 완료 | 파일: %s", save_result["file_path"])
            self.context.documents.previous_contents["changes"] = content
            return [save_result["file_path"]]

        logger.warning("changes 저장 실패")
        return []

    def _generate_openapi(
        self,
        output_dir: str,
        previous_results: Optional[Dict[str, Any]],
    ) -> List[str]:
        logger = self.agent_logger_factory("openapi")
        logger.info("openapi 문서 생성 시작")

        prompt = build_openapi_prompt(
            output_dir,
            previous_results=previous_results,
        )
        result = self.agents["openapi"](prompt)
        content = self.process_agent_result("openapi", result)
        self.validate_and_record("openapi", content)
        save_result = self.save_document("openapi", content)

        if save_result:
            logger.info("openapi 저장 완료 | 파일: %s", save_result["file_path"])
            self.context.documents.previous_contents["openapi"] = content
            return [save_result["file_path"]]

        logger.warning("openapi 저장 실패")
        return []
