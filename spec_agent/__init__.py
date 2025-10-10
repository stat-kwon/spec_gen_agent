"""
Strands Agent SDK based specification generation system.

This package provides a multi-agent system for generating service documentation
from FRS (Functional Requirements Specification) markdown files using the
Strands Agent SDK framework.
"""

from .orchestrator import AgenticOrchestrator
from .models import ServiceType

# Alias for backward compatibility
SpecOrchestrator = AgenticOrchestrator

__version__ = "2.0.0"
__all__ = ["AgenticOrchestrator", "SpecOrchestrator", "ServiceType"]
