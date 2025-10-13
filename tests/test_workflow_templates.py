import asyncio
import json
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


def test_apply_template_changes_tolerates_spacing_variants():
    content = """
# changes

## Version History / 버전 이력
기존 릴리스 정보

## 변경 요약 / Change Summary
- 주요 변경사항 나열

## 영향 / 위험 / Impact / Risk
- 영향과 위험 요소

## Rollback Plan / 롤백 계획
- 롤백 프로세스

## Known Issues / 알려진 문제
- 알려진 이슈
"""

    result = apply_template(content, "changes")

    assert result["success"] is True
    assert result["missing_sections"] == []


def test_parse_json_response_extracts_object_from_wrapped_text():
    config = Config(openai_api_key="test-key")
    workflow = SpecificationWorkflow(config=config)

    raw = (
        "아래는 개선된 결정입니다. 필요한 경우만 참고하세요. "
        '{"approved": false, "overall_quality": 68, "decision": "개선필요", '
        '"required_improvements": ['
        '{"document": "design", "note": "보안 다이어그램 업데이트"}'
        '], "message": "추가 수정 필요"}'
    )

    parsed = workflow._parse_json_response("coordinator", raw)

    assert parsed["approved"] is False
    assert parsed["overall_quality"] == 68
    assert parsed["required_improvements"] == [
        {"document": "design", "note": "보안 다이어그램 업데이트"}
    ]


def test_parse_json_response_handles_code_fences():
    config = Config(openai_api_key="test-key")
    workflow = SpecificationWorkflow(config=config)

    raw = """```json
{
  \"issues\": [],
  \"severity\": \"low\",
  \"cross_references\": 0,
  \"naming_conflicts\": 0
}
```"""

    parsed = workflow._parse_json_response("consistency_checker", raw)

    assert parsed == {
        "issues": [],
        "severity": "low",
        "cross_references": 0,
        "naming_conflicts": 0,
    }


def test_quality_cycle_applies_feedback_per_document(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key", max_iterations=1)
    workflow = SpecificationWorkflow(config=config)

    output_dir = tmp_path / "output"
    workflow.context['project'] = {
        'output_dir': str(output_dir),
        'frs_id': 'FRS-TEST',
        'service_type': ServiceType.API.value,
        'frs_content': '샘플 FRS',
    }

    base_documents = {
        'requirements': {'path': str(output_dir / 'requirements.md'), 'content': '# Requirements\n'},
        'design': {'path': str(output_dir / 'design.md'), 'content': '# Design\n'},
        'tasks': {'path': str(output_dir / 'tasks.md'), 'content': '# Tasks\n'},
    }

    def fake_load_documents(service_type):
        return {name: doc.copy() for name, doc in base_documents.items()}

    monkeypatch.setattr(workflow, '_load_generated_documents', fake_load_documents)

    quality_response = {
        'completeness': 70,
        'consistency': 65,
        'clarity': 68,
        'technical': 66,
        'overall': 67,
        'feedback': [
            {"document": "design", "note": "설계 다이어그램을 보강하세요."}
        ],
        'needs_improvement': True,
    }

    consistency_response = {
        'issues': [
            {"document": "tasks", "note": "설계 변경 사항을 작업 목록에 반영"}
        ],
        'severity': 'medium',
        'cross_references': 1,
        'naming_conflicts': 0,
    }

    coordinator_response = {
        'approved': False,
        'overall_quality': 68,
        'decision': '개선필요',
        'required_improvements': [
            {"document": "design", "note": "보안 섹션에 암호화 다이어그램 추가"},
            {"document": "tasks", "note": "보안 작업을 우선순위 높음으로 조정"},
        ],
        'message': '설계와 작업의 일관성을 맞춰주세요.',
    }

    workflow.agents = {
        'quality_assessor': lambda prompt: json.dumps(quality_response, ensure_ascii=False),
        'consistency_checker': lambda prompt: json.dumps(consistency_response, ensure_ascii=False),
        'coordinator': lambda prompt: json.dumps(coordinator_response, ensure_ascii=False),
    }

    requirements_calls = []
    design_calls = []
    tasks_calls = []

    def requirements_agent(prompt):
        requirements_calls.append(prompt)
        return '# Requirements\n'

    workflow.agents['requirements'] = requirements_agent

    def design_agent(prompt):
        design_calls.append(prompt)
        return '# Updated Design\n'

    def tasks_agent(prompt):
        tasks_calls.append(prompt)
        return '# Updated Tasks\n'

    workflow.agents['design'] = design_agent
    workflow.agents['tasks'] = tasks_agent

    def fake_validate(agent_name, content):
        workflow.context['documents'].setdefault('previous_contents', {})[agent_name] = content
        workflow.context['documents'].setdefault('template_results', {})[agent_name] = {'success': True}
        return {'success': True}

    def fake_save(agent_name, content):
        path = output_dir / ('openapi.json' if agent_name == 'openapi' else f'{agent_name}.md')
        return {'file_path': str(path)}

    monkeypatch.setattr(workflow, '_validate_and_record_template', fake_validate)
    monkeypatch.setattr(workflow, '_save_agent_document_sync', fake_save)

    result = asyncio.run(workflow._run_quality_improvement_cycle(ServiceType.API))

    assert result['improvement_applied'] is True
    assert any(path.endswith('design.md') for path in result['updated_files'])
    assert any(path.endswith('tasks.md') for path in result['updated_files'])
    assert not any('requirements.md' in path for path in result['updated_files'])

    assert len(design_calls) == 1
    assert len(tasks_calls) == 1
    assert requirements_calls == []
