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
from spec_agent.tools.template_tools import apply_template


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


def test_sequential_workflow_prompts_use_absolute_paths(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key")
    workflow = SpecificationWorkflow(config=config)

    project_output = tmp_path / "output"
    workflow.context['project'] = {
        'frs_content': '샘플 FRS',
        'output_dir': str(project_output),
        'frs_id': 'FRS-TEST',
        'service_type': ServiceType.API.value,
    }

    captured_prompts = {}

    def record_prompt(name, response):
        def _inner(prompt):
            captured_prompts[name] = prompt
            return response

        return _inner

    workflow.agents = {
        'requirements': record_prompt('requirements', "# Requirements\n- 내용"),
        'design': record_prompt('design', "# Design\n- 내용"),
        'tasks': record_prompt('tasks', "# Tasks\n- 내용"),
        'changes': record_prompt('changes', "# Changes\n- 내용"),
        'openapi': record_prompt('openapi', "{}"),
    }

    def successful_apply_template(content, template_type):
        return {
            'success': True,
            'content': content,
            'template_type': template_type,
        }

    def successful_validate_openapi_spec(content):
        return {
            'success': True,
            'content': content,
        }

    monkeypatch.setattr('spec_agent.workflow.apply_template', successful_apply_template)
    monkeypatch.setattr('spec_agent.workflow.validate_openapi_spec', successful_validate_openapi_spec)

    result = asyncio.run(workflow._execute_sequential_workflow(ServiceType.API))

    assert result['success'] is True

    resolved_output = str(project_output.resolve())
    requirements_path = str(Path(resolved_output) / "requirements.md")
    design_path = str(Path(resolved_output) / "design.md")
    tasks_path = str(Path(resolved_output) / "tasks.md")

    assert f'read_spec_file("{requirements_path}")' in captured_prompts['design']
    assert f'read_spec_file("{design_path}")' in captured_prompts['tasks']

    changes_prompt = captured_prompts['changes']
    for path in (requirements_path, design_path, tasks_path):
        assert f'read_spec_file("{path}")' in changes_prompt

    openapi_prompt = captured_prompts['openapi']
    assert f'read_spec_file("{requirements_path}")' in openapi_prompt
    assert f'read_spec_file("{design_path}")' in openapi_prompt


def test_apply_template_allows_headings_without_space():
    content = """
#헤더/메타
기본 메타 정보

# 범위
시스템 범위 설명

# 기능 요구사항
## REQ-001: 항목
- **설명**: 테스트
- **우선순위**: 높음
- **종속성**: 없음
- **수용 기준**: 기준

# 오류 요구사항
에러 처리 정책

##보안 ＆ 개인정보/Security & Privacy
보안 및 개인정보 보호 항목

# 관측 가능성
모니터링 요구사항

# 수용 기준
테스트 기준 요약
"""

    result = apply_template(content, "requirements")

    assert result["success"] is True
    assert result["missing_sections"] == []
