"""Strands Agent SDK 기반 명세서 생성 에이전트들."""

from typing import Optional

from strands import Agent
from strands.models.openai import OpenAIModel

from spec_agent.utils.logging import get_agent_logger
from spec_agent.utils import get_system_prompt
from ..tools import (
    load_frs_document,
    extract_frs_metadata,
    apply_template,
    validate_markdown_structure,
    read_spec_file,
    list_spec_files,
)
from ..config import Config
from .factory import StrandsAgentFactory


def create_requirements_agent(
    config: Config,
    *,
    session_id: Optional[str] = None,
) -> Agent:
    """
    Strands SDK를 활용한 요구사항 생성 에이전트 생성.

    Returns:
        향상된 요구사항 생성 Strands Agent
    """
    logger = get_agent_logger(session_id, "requirements")
    logger.info("요구사항 에이전트 프롬프트 구성 시작")

    factory = StrandsAgentFactory(config, session_id=session_id)

    agent = factory.create_agent(
        agent_type="requirements",
        system_prompt=get_system_prompt("requirements"),
        tools=[
            load_frs_document,
            extract_frs_metadata,
            apply_template,
            validate_markdown_structure,
        ],
        session_id=session_id,
    )
    logger.info("요구사항 에이전트 생성 완료")
    return agent


def create_design_agent(
    config: Config,
    *,
    session_id: Optional[str] = None,
) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 설계 생성 에이전트 생성.

    Returns:
        향상된 설계 생성 Strands Agent
    """
    logger = get_agent_logger(session_id, "design")
    logger.info("설계 에이전트 프롬프트 구성 시작")

    factory = StrandsAgentFactory(config, session_id=session_id)
    system_prompt = get_system_prompt("design")

    agent = factory.create_agent(
        agent_type="design",
        system_prompt=system_prompt,
        tools=[apply_template, validate_markdown_structure, read_spec_file],
        temperature=0.6,  # 창의적 설계를 위해 약간 높은 temperature
        session_id=session_id,
    )
    logger.info("설계 에이전트 생성 완료")
    return agent


def create_tasks_agent(
    config: Config,
    *,
    session_id: Optional[str] = None,
) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 작업 분해 에이전트 생성.

    Returns:
        향상된 작업 생성 Strands Agent
    """
    logger = get_agent_logger(session_id, "tasks")
    logger.info("작업 분해 에이전트 프롬프트 구성 시작")

    factory = StrandsAgentFactory(config, session_id=session_id)
    system_prompt = get_system_prompt("tasks")

    agent = factory.create_agent(
        agent_type="tasks",
        system_prompt=system_prompt,
        tools=[apply_template, validate_markdown_structure, read_spec_file],
        session_id=session_id,
    )
    logger.info("작업 분해 에이전트 생성 완료")
    return agent


def create_changes_agent(
    config: Config,
    *,
    session_id: Optional[str] = None,
) -> Agent:
    """
    Strands SDK의 고급 기능을 활용한 변경사항 문서화 에이전트 생성.

    Returns:
        향상된 변경사항 생성 Strands Agent
    """
    logger = get_agent_logger(session_id, "changes")
    logger.info("변경 관리 에이전트 프롬프트 구성 시작")

    factory = StrandsAgentFactory(config, session_id=session_id)
    system_prompt = get_system_prompt("changes")

    agent = factory.create_agent(
        agent_type="changes",
        system_prompt=system_prompt,
        tools=[apply_template, validate_markdown_structure, read_spec_file],
        session_id=session_id,
    )
    logger.info("변경 관리 에이전트 생성 완료")
    return agent


def create_openapi_agent(
    config: Config,
    *,
    session_id: Optional[str] = None,
) -> Agent:
    """
    Strands SDK를 사용하여 OpenAPI 명세 에이전트를 생성합니다.

    Returns:
        OpenAPI 생성을 위해 구성된 Strands Agent
    """
    logger = get_agent_logger(session_id, "openapi")
    logger.info("OpenAPI 에이전트 초기화")
    system_prompt = get_system_prompt("openapi")

    openai_model = OpenAIModel(
        model_id=config.openai_model,
        params={"temperature": config.openai_temperature},
        client_args={"api_key": config.openai_api_key},
    )

    agent = Agent(model=openai_model, tools=[], system_prompt=system_prompt)
    logger.info("OpenAPI 에이전트 준비 완료")
    return agent


def create_quality_assessor_agent(config: Config) -> Agent:
    """
    문서 품질을 평가하는 전문 에이전트 생성 (Agentic 개선 버전).

    Returns:
        품질 평가를 위해 구성된 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    return factory.create_agent(
        agent_type="quality_assessor",
        system_prompt=get_system_prompt("quality_assessor"),
        tools=[list_spec_files, read_spec_file],
        temperature=0.1,  # 일관된 평가를 위해 낮은 temperature
    )


def create_consistency_checker_agent(config: Config) -> Agent:
    """
    문서 간 일관성을 검증하는 전문 에이전트 생성.

    Returns:
        일관성 검증을 위해 구성된 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    return factory.create_agent(
        agent_type="consistency_checker",
        system_prompt=get_system_prompt("consistency_checker"),
        tools=[list_spec_files, read_spec_file],
        temperature=0.1,  # 일관된 검증을 위해 낮은 temperature
    )


def create_coordinator_agent(config: Config) -> Agent:
    """
    최종 승인 결정을 내리는 코디네이터 에이전트 생성 (Agentic 개선 버전).

    Returns:
        최종 승인 결정을 위해 구성된 Strands Agent
    """
    factory = StrandsAgentFactory(config)
    return factory.create_agent(
        agent_type="coordinator",
        system_prompt=get_system_prompt("coordinator"),
        tools=[list_spec_files, read_spec_file],
        temperature=0.0,
    )
