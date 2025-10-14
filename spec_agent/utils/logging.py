"""Logging utilities for spec_agent.

Provides consistent logging configuration and helper adapters to trace
agent interactions throughout the workflow.
"""

from __future__ import annotations

import logging
from typing import Union

DEFAULT_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class SessionLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that prefixes messages with the session identifier."""

    def process(self, msg: str, kwargs):  # type: ignore[override]
        session = self.extra.get("session")
        if session:
            msg = f"[세션 {session}] {msg}"
        return msg, kwargs


class AgentLoggerAdapter(SessionLoggerAdapter):
    """Logger adapter that highlights agent specific context."""

    def process(self, msg: str, kwargs):  # type: ignore[override]
        session = self.extra.get("session")
        agent = self.extra.get("agent")
        prefixes = []
        if session:
            prefixes.append(f"세션 {session}")
        if agent:
            prefixes.append(f"Agent {agent}")
        if prefixes:
            prefix = " | ".join(prefixes)
            msg = f"[{prefix}] {msg}"
        return msg, kwargs


def configure_logging(level: Union[int, str] = logging.INFO) -> None:
    """Configure the base logger for the spec_agent package.

    Args:
        level: Logging level or level name to apply. Defaults to INFO.
    """

    if isinstance(level, str):
        level_value = getattr(logging, level.upper(), logging.INFO)
    else:
        level_value = level

    package_logger = logging.getLogger("spec_agent")
    if not package_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT))
        package_logger.addHandler(handler)
    package_logger.setLevel(level_value)
    package_logger.propagate = False

    logging.captureWarnings(True)


def get_session_logger(component: str, session_id: str) -> SessionLoggerAdapter:
    """Return a logger adapter scoped to a workflow session."""

    logger = logging.getLogger(f"spec_agent.{component}")
    return SessionLoggerAdapter(logger, {"session": session_id})


def get_agent_logger(session_id: str, agent_name: str) -> AgentLoggerAdapter:
    """Return a logger adapter that includes agent context."""

    logger = logging.getLogger(f"spec_agent.agents.{agent_name}")
    return AgentLoggerAdapter(logger, {"session": session_id, "agent": agent_name})
