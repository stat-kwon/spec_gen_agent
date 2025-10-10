"""
Strands Agent SDK based specification generation system.

This package provides a multi-agent system for generating service documentation
from FRS (Functional Requirements Specification) markdown files using the
Strands Agent SDK framework.
"""

from .workflow import SpecificationWorkflow
from .models import ServiceType

__version__ = "2.0.0"
__all__ = ["SpecificationWorkflow", "ServiceType"]
