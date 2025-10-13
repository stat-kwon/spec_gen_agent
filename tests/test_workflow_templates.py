import asyncio
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spec_agent.config import Config
from spec_agent.models import ServiceType
from spec_agent.workflow import SpecificationWorkflow


def test_apply_template_failure_prevents_save(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key")
    workflow = SpecificationWorkflow(config=config)

    workflow.context['project'] = {
        'frs_content': '샘플 FRS',
        'output_dir': str(tmp_path),
        'frs_id': 'FRS-TEST',
        'service_type': ServiceType.API.value,
    }

    workflow.agents = {
        'requirements': lambda prompt: "# 잘못된 문서\n내용만 존재",
        'design': lambda prompt: "",
        'tasks': lambda prompt: "",
        'changes': lambda prompt: "",
        'openapi': lambda prompt: "{}",
    }

    def failing_apply_template(content, template_type):
        return {
            'success': False,
            'content': content,
            'template_type': template_type,
            'missing_sections': ['Scope'],
            'required_sections': ['Scope'],
        }

    monkeypatch.setattr('spec_agent.workflow.apply_template', failing_apply_template)

    result = asyncio.run(workflow._execute_sequential_workflow(ServiceType.API))

    assert result['success'] is False
    assert not any(tmp_path.iterdir())
    assert workflow.saved_files == []
    assert workflow.context['documents']['template_results']['requirements']['success'] is False
    assert 'Scope' in workflow.context['documents']['template_results']['requirements']['missing_sections']
