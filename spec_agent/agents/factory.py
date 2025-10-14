"""Agent factory utilities for Strands-based agents."""

from __future__ import annotations

import logging
from typing import Optional

from strands import Agent
from strands.models.openai import OpenAIModel

from spec_agent.utils.logging import get_session_logger
from ..config import Config


LOGGER = logging.getLogger("spec_agent.agents.factory")


class StrandsAgentFactory:
    """Create Strands agents with shared configuration and logging context."""

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
        """Instantiate a Strands agent with shared model configuration."""

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
