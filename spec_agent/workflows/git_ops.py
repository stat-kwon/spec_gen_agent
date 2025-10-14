from typing import Callable, Dict, List
import logging

from spec_agent.tools import create_git_branch, commit_changes

from .context import WorkflowContext


ToolKwargsResolver = Callable[[Callable[..., Dict]], Dict]


def setup_git_branch(
    context: WorkflowContext,
    resolve_tool_kwargs: ToolKwargsResolver,
    logger: logging.LoggerAdapter,
) -> Dict:
    """Git 브랜치를 준비합니다."""

    frs_id = context.project.get("frs_id")
    service_type = context.project.get("service_type")

    git_result = create_git_branch(
        frs_id,
        service_type,
        **resolve_tool_kwargs(create_git_branch),
    )
    if git_result.get("success"):
        logger.info("Git 브랜치 생성 완료 | 이름: %s", git_result.get("branch_name"))
    else:
        logger.warning("Git 브랜치 생성 실패 | 이유: %s", git_result.get("error"))
    return git_result


def commit_generated_changes(
    context: WorkflowContext,
    files_written: List[str],
    resolve_tool_kwargs: ToolKwargsResolver,
    logger: logging.LoggerAdapter,
) -> Dict:
    """생성된 문서를 Git에 커밋합니다."""

    frs_id = context.project.get("frs_id")
    service_type = context.project.get("service_type")

    result = commit_changes(
        frs_id,
        service_type,
        files_written,
        **resolve_tool_kwargs(commit_changes),
    )

    if result.get("success"):
        logger.info(
            "Git 커밋 완료 | 해시: %s",
            (result.get("commit_hash") or "")[:8],
        )
    else:
        logger.warning("Git 커밋 실패 | 이유: %s", result.get("error"))
    return result
