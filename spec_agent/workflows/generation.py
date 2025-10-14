from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import logging

from spec_agent.models import ServiceType

from .context import WorkflowContext
from .prompts import (
    build_changes_prompt,
    build_design_prompt,
    build_openapi_prompt,
    build_requirements_prompt,
    build_tasks_prompt,
)

AgentLoggerFactory = Callable[[str], logging.LoggerAdapter]
AgentCallable = Callable[[Any], Any]
ProcessResultFn = Callable[[str, Any], str]
ValidateTemplateFn = Callable[[str, str], Dict[str, Any]]
SaveDocumentFn = Callable[[str, str], Optional[Dict[str, Any]]]


class SequentialDocumentGenerator:
    """순차 문서 생성을 담당합니다."""

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

    async def run(self, service_type: ServiceType) -> Dict[str, Any]:
        """문서를 순차적으로 생성합니다."""

        self.logger.info("순차적 파일 기반 워크플로우 실행 시작")

        try:
            saved_files: List[str] = []
            output_dir = str(Path(self.context.project.get("output_dir", "")).resolve())

            frs_content = self.context.project.get("frs_content", "No FRS Contents")
            requirements_logger = self.agent_logger_factory("requirements")
            requirements_logger.info("문서 생성 시작")
            req_prompt = build_requirements_prompt(
                frs_content,
                self.context.project.get("service_type", service_type.value),
                previous_results=self.context.quality.get("previous_results"),
                metadata=self.context.metrics,
            )
            req_result = self.agents["requirements"](req_prompt)
            req_content = self.process_agent_result("requirements", req_result)
            self.validate_and_record("requirements", req_content)
            save_result = self.save_document("requirements", req_content)
            if save_result:
                saved_files.append(save_result["file_path"])
                requirements_logger.info(
                    "문서 생성 완료 | 파일: %s", save_result["file_path"]
                )
            else:
                requirements_logger.warning("문서 저장 실패")
            self.context.documents.previous_contents["requirements"] = req_content

            design_logger = self.agent_logger_factory("design")
            design_logger.info("문서 생성 시작")
            design_prompt = build_design_prompt(output_dir, service_type.value)
            design_result = self.agents["design"](design_prompt)
            design_content = self.process_agent_result("design", design_result)
            self.validate_and_record("design", design_content)
            save_result = self.save_document("design", design_content)
            if save_result:
                saved_files.append(save_result["file_path"])
                design_logger.info(
                    "문서 생성 완료 | 파일: %s", save_result["file_path"]
                )
            else:
                design_logger.warning("문서 저장 실패")
            self.context.documents.previous_contents["design"] = design_content

            tasks_logger = self.agent_logger_factory("tasks")
            tasks_logger.info("문서 생성 시작")
            tasks_prompt = build_tasks_prompt(output_dir)
            tasks_result = self.agents["tasks"](tasks_prompt)
            tasks_content = self.process_agent_result("tasks", tasks_result)
            self.validate_and_record("tasks", tasks_content)
            save_result = self.save_document("tasks", tasks_content)
            if save_result:
                saved_files.append(save_result["file_path"])
                tasks_logger.info("문서 생성 완료 | 파일: %s", save_result["file_path"])
            else:
                tasks_logger.warning("문서 저장 실패")
            self.context.documents.previous_contents["tasks"] = tasks_content

            changes_logger = self.agent_logger_factory("changes")
            changes_logger.info("문서 생성 시작")
            changes_prompt = build_changes_prompt(output_dir, service_type.value)
            changes_result = self.agents["changes"](changes_prompt)
            changes_content = self.process_agent_result("changes", changes_result)
            self.validate_and_record("changes", changes_content)
            save_result = self.save_document("changes", changes_content)
            if save_result:
                saved_files.append(save_result["file_path"])
                changes_logger.info(
                    "문서 생성 완료 | 파일: %s", save_result["file_path"]
                )
            else:
                changes_logger.warning("문서 저장 실패")
            self.context.documents.previous_contents["changes"] = changes_content

            if service_type == ServiceType.API:
                openapi_logger = self.agent_logger_factory("openapi")
                openapi_logger.info("문서 생성 시작")
                openapi_prompt = build_openapi_prompt(output_dir)
                openapi_result = self.agents["openapi"](openapi_prompt)
                openapi_content = self.process_agent_result("openapi", openapi_result)
                self.validate_and_record("openapi", openapi_content)
                save_result = self.save_document("openapi", openapi_content)
                if save_result:
                    saved_files.append(save_result["file_path"])
                    openapi_logger.info(
                        "문서 생성 완료 | 파일: %s", save_result["file_path"]
                    )
                else:
                    openapi_logger.warning("문서 저장 실패")
                self.context.documents.previous_contents["openapi"] = openapi_content

            self.logger.info(
                "순차적 워크플로우 종료 | 저장 파일 %d개", len(saved_files)
            )
            return {
                "success": True,
                "saved_files": saved_files,
                "execution_type": "sequential",
            }

        except Exception as exc:
            self.logger.exception("순차적 워크플로우 실패")
            return {"success": False, "error": str(exc)}
