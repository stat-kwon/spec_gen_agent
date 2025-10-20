"""Strands Agent SDK 기반 명세서 생성 에이전트."""

from __future__ import annotations

import logging
from importlib import import_module
from typing import Any, Callable, Optional

from strands import Agent
from strands.models.openai import OpenAIModel

from spec_agent.utils.logging import get_session_logger
from ..config import Config

LOGGER = logging.getLogger("spec_agent.agents.factory")


class StrandsAgentFactory:
    """Strands 기반 에이전트를 생성하는 팩토리."""

    def __init__(self, config: Config, session_id: Optional[str] = None):
        self.config = config
        self.session_id = session_id
        self.base_model_config = {
            "model_id": config.openai_model,
            "params": {"temperature": config.openai_temperature},
            "client_args": {"api_key": config.openai_api_key},
        }
        self.logger = (
            get_session_logger("agents.factory", session_id) if session_id else LOGGER
        )
        self.logger.info("StrandsAgentFactory 초기화")

    def create_agent(
        self,
        agent_type: str,
        system_prompt: str,
        tools: list,
        temperature: Optional[float] = None,
        session_id: Optional[str] = None,
    ) -> Agent:
        """공통 모델 설정을 공유하는 Strands 에이전트를 생성합니다."""

        logger = (
            get_session_logger("agents.factory", session_id)
            if session_id
            else self.logger
        )
        logger.info("에이전트 생성 시작 | 타입=%s", agent_type)

        model_config = self.base_model_config.copy()
        if temperature is not None:
            model_config["params"]["temperature"] = temperature

        model = OpenAIModel(**model_config)
        agent = Agent(model=model, tools=tools, system_prompt=system_prompt)

        logger.info("에이전트 생성 완료 | 타입=%s", agent_type)
        return agent


_SPEC_AGENT_MODULE = None


def _load_spec_agents():
    global _SPEC_AGENT_MODULE
    if _SPEC_AGENT_MODULE is None:
        _SPEC_AGENT_MODULE = import_module("spec_agent.agents.spec_agents")
    return _SPEC_AGENT_MODULE


def _delegate(name: str) -> Callable[..., Any]:
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        module = _load_spec_agents()
        func = getattr(module, name)
        if wrapper.__doc__ is None:
            wrapper.__doc__ = func.__doc__
        return func(*args, **kwargs)

    wrapper.__name__ = name
    wrapper.__doc__ = None
    return wrapper


create_requirements_agent = _delegate("create_requirements_agent")
create_design_agent = _delegate("create_design_agent")
create_tasks_agent = _delegate("create_tasks_agent")
create_changes_agent = _delegate("create_changes_agent")
create_openapi_agent = _delegate("create_openapi_agent")
create_coordinator_agent = _delegate("create_coordinator_agent")
create_quality_assessor_agent = _delegate("create_quality_assessor_agent")
create_consistency_checker_agent = _delegate("create_consistency_checker_agent")


__all__ = [
    "StrandsAgentFactory",
    "create_requirements_agent",
    "create_design_agent",
    "create_tasks_agent",
    "create_changes_agent",
    "create_openapi_agent",
    "create_coordinator_agent",
    "create_quality_assessor_agent",
    "create_consistency_checker_agent",
]
