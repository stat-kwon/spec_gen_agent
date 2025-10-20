import asyncio
import json
import logging
from pathlib import Path
import sys
from typing import Dict, List, Tuple

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from spec_agent.config import Config
from spec_agent.models import ServiceType
from spec_agent.workflows import SpecificationWorkflowRunner
from spec_agent.workflows.generation import DocumentGenerationPhase
from spec_agent.workflows.quality_feedback import QualityFeedbackPhase
from spec_agent.workflows.quality_improvement import QualityImprovementPhase
from spec_agent.tools.template_tools import apply_template


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def build_document_phase(runner: SpecificationWorkflowRunner) -> DocumentGenerationPhase:
    return DocumentGenerationPhase(
        context=runner.context,
        agents=runner.agents,
        logger=runner.logger,
        agent_logger_factory=runner._get_agent_logger,
        process_agent_result=runner._process_agent_result,
        validate_and_record=runner._validate_and_record_template,
        save_document=runner._save_document,
    )


def build_quality_phase(
    runner: SpecificationWorkflowRunner,
) -> Tuple[QualityImprovementPhase, QualityFeedbackPhase]:
    improvement = QualityImprovementPhase(
        context=runner.context,
        agents=runner.agents,
        logger=runner.logger,
        agent_logger_factory=runner._get_agent_logger,
        document_order=runner._get_document_agent_order,
        feedback_tracker=runner.feedback_tracker,
        max_iterations=getattr(runner.config, "max_iterations", 1),
        quality_threshold=getattr(runner.config, "quality_threshold", 0.0),
    )
    feedback = QualityFeedbackPhase(
        context=runner.context,
        agents=runner.agents,
        logger=runner.logger,
        agent_logger_factory=runner._get_agent_logger,
        document_order=runner._get_document_agent_order,
        process_agent_result=runner._process_agent_result,
        validate_and_record=runner._validate_and_record_template,
        save_document=runner._save_document,
        feedback_tracker=runner.feedback_tracker,
    )
    return improvement, feedback


# ---------------------------------------------------------------------------
# Document generation tests
# ---------------------------------------------------------------------------


def test_document_generation_stops_on_template_failure(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key")
    runner = SpecificationWorkflowRunner(config=config)
    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "frs_content": "샘플 FRS",
        "output_dir": str(tmp_path),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
    }

    runner.agents = {
        "requirements": lambda prompt: "# 잘못된 문서\n내용만 존재",
        "design": lambda prompt: "",
        "tasks": lambda prompt: "",
        "changes": lambda prompt: "",
        "openapi": lambda prompt: "{}",
    }

    def failing_apply_template(content, template_type):
        return {
            "success": False,
            "content": content,
            "template_type": template_type,
            "missing_sections": ["Scope"],
            "required_sections": ["Scope"],
        }

    runner._get_apply_template_fn = lambda: failing_apply_template

    def fail_if_called(*_):
        raise AssertionError("문서가 저장되면 안 됩니다")

    runner._save_document = fail_if_called

    document_phase = build_document_phase(runner)
    result = asyncio.run(document_phase.execute(ServiceType.API))

    assert result["success"] is False
    assert runner.storage.saved_files() == []
    template_result = runner.context.documents.template_results["requirements"]
    assert template_result["success"] is False
    assert "Scope" in template_result["missing_sections"]


def test_document_generation_prompts_use_absolute_paths(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key")
    runner = SpecificationWorkflowRunner(config=config)

    project_output = tmp_path / "output"
    project_output.mkdir()
    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "frs_content": "샘플 FRS",
        "output_dir": str(project_output),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
    }

    captured_prompts: Dict[str, str] = {}

    def record_prompt(name: str, response: str):
        def _inner(prompt: str) -> str:
            captured_prompts[name] = prompt
            return response

        return _inner

    runner.agents = {
        "requirements": record_prompt("requirements", "# Requirements\n- 내용"),
        "design": record_prompt("design", "# Design\n- 내용"),
        "tasks": record_prompt("tasks", "# Tasks\n- 내용"),
        "changes": record_prompt("changes", "# Changes\n- 내용"),
        "openapi": record_prompt("openapi", "{}"),
    }

    runner._get_apply_template_fn = lambda: (
        lambda content, template_type: {
            "success": True,
            "content": content,
            "template_type": template_type,
        }
    )
    runner._get_validate_openapi_spec_fn = lambda: (
        lambda content: {"success": True, "content": content}
    )

    def fake_save(agent_name: str, content: str):
        path = project_output / (
            "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        )
        return {
            "filename": path.name,
            "file_path": str(path),
            "size": len(content),
            "action": "test",
        }

    runner._save_document = fake_save

    document_phase = build_document_phase(runner)
    result = asyncio.run(document_phase.execute(ServiceType.API))

    assert result["success"] is True
    requirements_prompt = captured_prompts["requirements"]
    assert 'load_frs_document("' in requirements_prompt
    assert str(tmp_path / "FRS-SAMPLE.md") in requirements_prompt

    resolved_output = str(project_output.resolve())
    requirements_path = str(Path(resolved_output) / "requirements.md")
    design_path = str(Path(resolved_output) / "design.md")
    tasks_path = str(Path(resolved_output) / "tasks.md")

    assert f'read_spec_file("{requirements_path}")' in captured_prompts["design"]
    assert f'read_spec_file("{design_path}")' in captured_prompts["tasks"]

    changes_prompt = captured_prompts["changes"]
    for path in (requirements_path, design_path, tasks_path):
        assert f'read_spec_file("{path}")' in changes_prompt

    openapi_prompt = captured_prompts["openapi"]
    assert f'read_spec_file("{requirements_path}")' in openapi_prompt
    assert f'read_spec_file("{design_path}")' in openapi_prompt


# ---------------------------------------------------------------------------
# Template validation helpers (unchanged)
# ---------------------------------------------------------------------------


def test_apply_template_allows_headings_without_space():
    content = """
# Feature Specification: Sample Feature

**Feature Branch**: `[123-sample-feature]`  
**Created**: 2024-01-01  
**Status**: Draft  
**Input**: User description: "Sample"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Onboard user (Priority: P1)
사용자 스토리 설명

**Why this priority**: 핵심 온보딩 흐름

**Independent Test**: 새 계정으로 온보딩 흐름 실행 후 완료 확인

**Acceptance Scenarios**:
1. **Given** 새 이용자, **When** 온보딩을 완료하면, **Then** 환영 화면을 본다

### Edge Cases
- 네트워크 지연 시 재시도 처리

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: 온보딩 흐름은 2분 이내에 완료되어야 한다

### Key Entities *(include if feature involves data)*
- **UserProfile**: 온보딩 상태, 완료 시각 포함

## Success Criteria *(mandatory)*

### Measurable Outcomes
- **SC-001**: 95% 사용자가 첫 시도에 온보딩을 마친다
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


def test_apply_template_design_matches_plan_structure():
    content = """
# Implementation Plan: Sample Feature

**Branch**: `[123-sample-feature]` | **Date**: 2024-01-01 | **Spec**: `/specs/sample/requirements.md`
**Input**: Feature specification from `/specs/sample/requirements.md`

## Summary
- 핵심 목표 요약

## Technical Context
**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI  
**Storage**: PostgreSQL  
**Testing**: pytest  
**Target Platform**: Kubernetes  
**Project Type**: single  
**Performance Goals**: P95 300ms  
**Constraints**: GDPR  
**Scale/Scope**: 10k users

## Constitution Check
- ✅ 규칙 준수 확인

## Project Structure

### Documentation (this feature)
```
specs/sample/
├── plan.md
└── requirements.md
```

### Source Code (repository root)
```
src/
└── api/
```

**Structure Decision**: 단일 서비스 유지

## Complexity Tracking
| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|---------------------------------------|
| 없음 | 현재 없음 | - |
"""

    result = apply_template(content, "design")

    assert result["success"] is True
    assert result["missing_sections"] == []


def test_apply_template_tasks_matches_spec_template():
    content = """
# Tasks: Sample Feature

**Input**: Design documents from `/specs/sample/`
**Prerequisites**: plan.md, requirements.md

**Tests**: 계약 테스트 필수
**Organization**: 사용자 스토리별 Phase로 구성

## Format: `[ID] [P?] [Story] Description`
- 규칙 설명

## Path Conventions
- src/ 구조 서술

## Phase 1: Setup (Shared Infrastructure)
- [ ] T001 [P] [US-Setup] 초기 구성

## Phase 2: Foundational (Blocking Prerequisites)
- [ ] T002 [US-Found] 핵심 인프라

## Phase N: Polish & Cross-Cutting Concerns
- [ ] T099 [US-Polish] 문서 정비

## Dependencies & Execution Order
- Phase 의존 관계 설명

## Implementation Strategy
### MVP First (User Story 1 Only)
- 단계적 배포 전략

### Incremental Delivery
- 순차 배포 전략

### Parallel Team Strategy
- 병렬 전략

## Notes
- 추가 참고 사항
"""

    result = apply_template(content, "tasks")

    assert result["success"] is True
    assert result["missing_sections"] == []


# ---------------------------------------------------------------------------
# JSON 파싱 및 보정 테스트
# ---------------------------------------------------------------------------


def test_parse_json_response_extracts_object_from_wrapped_text():
    config = Config(openai_api_key="test-key")
    runner = SpecificationWorkflowRunner(config=config)
    quality_phase, _ = build_quality_phase(runner)

    raw = (
        "아래는 개선된 결정입니다. 필요한 경우만 참고하세요. "
        '{"approved": false, "overall_quality": 68, "decision": "개선필요", '
        '"required_improvements": ['
        '{"document": "design", "note": "보안 다이어그램 업데이트"}'
        '], "message": "추가 수정 필요"}'
    )

    parsed = quality_phase._parse_json_response("coordinator", raw)

    assert parsed["approved"] is False
    assert parsed["overall_quality"] == 68
    assert parsed["required_improvements"] == [
        {"document": "design", "note": "보안 다이어그램 업데이트"}
    ]


def test_parse_json_response_handles_code_fences():
    config = Config(openai_api_key="test-key")
    runner = SpecificationWorkflowRunner(config=config)
    quality_phase, _ = build_quality_phase(runner)

    raw = """```json
{
  "issues": [],
  "severity": "low",
  "cross_references": 0,
  "naming_conflicts": 0
}
```"""

    parsed = quality_phase._parse_json_response("consistency_checker", raw)

    assert parsed == {
        "issues": [],
        "severity": "low",
        "cross_references": 0,
        "naming_conflicts": 0,
    }


def test_parse_json_with_repair_preserves_apostrophes():
    config = Config(openai_api_key="test-key")
    runner = SpecificationWorkflowRunner(config=config)

    raw = "{'info': {'description': \"서비스 사용자의 요구를 반영했습니다.\", 'note': \"It's tricky\"}}"

    parsed = runner._parse_json_with_repair(raw)

    assert parsed["info"]["description"] == "서비스 사용자의 요구를 반영했습니다."
    assert parsed["info"]["note"] == "It's tricky"


def test_parse_json_with_repair_supports_mixed_tokens():
    config = Config(openai_api_key="test-key")
    runner = SpecificationWorkflowRunner(config=config)

    raw = "{info: {'enabled': True, 'metadata': null, 'details': {'deprecated': false}}}"

    parsed = runner._parse_json_with_repair(raw)

    assert parsed["info"]["enabled"] is True
    assert parsed["info"]["metadata"] is None
    assert parsed["info"]["details"]["deprecated"] is False


# ---------------------------------------------------------------------------
# 품질 개선 사이클 테스트
# ---------------------------------------------------------------------------


def test_quality_cycle_applies_feedback_per_document(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key", max_iterations=1)
    runner = SpecificationWorkflowRunner(config=config)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "output_dir": str(output_dir),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
        "frs_content": "샘플 FRS",
    }

    base_documents = {
        "requirements": {
            "path": str(output_dir / "requirements.md"),
            "content": "# Requirements\n",
        },
        "design": {"path": str(output_dir / "design.md"), "content": "# Design\n"},
        "tasks": {"path": str(output_dir / "tasks.md"), "content": "# Tasks\n"},
    }

    def fake_load_documents(service_type):
        return {name: doc.copy() for name, doc in base_documents.items()}

    quality_response = {
        "completeness": 70,
        "consistency": 65,
        "clarity": 68,
        "technical": 66,
        "overall": 67,
        "feedback": [{"document": "design", "note": "설계 다이어그램을 보강하세요."}],
        "needs_improvement": True,
    }

    consistency_response = {
        "issues": [{"document": "tasks", "note": "설계 변경 사항을 작업 목록에 반영"}],
        "severity": "medium",
        "cross_references": 1,
        "naming_conflicts": 0,
    }

    coordinator_response = {
        "approved": False,
        "overall_quality": 68,
        "decision": "개선필요",
        "required_improvements": [
            {"document": "design", "note": "보안 섹션에 암호화 다이어그램 추가"},
            {"document": "tasks", "note": "보안 작업을 우선순위 높음으로 조정"},
        ],
        "message": "설계와 작업의 일관성을 맞춰주세요.",
    }

    runner.agents = {
        "requirements": lambda prompt: "# Requirements\n",
        "design": lambda prompt: "# Updated Design\n",
        "tasks": lambda prompt: "# Updated Tasks\n",
        "changes": lambda prompt: "# Changes\n",
        "openapi": lambda prompt: "{}",
        "quality_assessor": lambda prompt: json.dumps(quality_response, ensure_ascii=False),
        "consistency_checker": lambda prompt: json.dumps(
            consistency_response, ensure_ascii=False
        ),
        "coordinator": lambda prompt: json.dumps(
            coordinator_response, ensure_ascii=False
        ),
    }

    def fake_validate(agent_name, content):
        runner.context.documents.previous_contents[agent_name] = content
        runner.context.documents.template_results[agent_name] = {"success": True}
        return {"success": True}

    runner._validate_and_record_template = fake_validate

    def fake_save(agent_name, content):
        path = output_dir / (
            "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        )
        return {
            "filename": path.name,
            "file_path": str(path),
            "size": len(content),
            "action": "test",
        }

    runner._save_document = fake_save

    quality_phase, feedback_phase = build_quality_phase(runner)
    monkeypatch.setattr(quality_phase, "_load_generated_documents", fake_load_documents)

    result = asyncio.run(quality_phase.execute(ServiceType.API, feedback_phase))

    assert result["improvement_applied"] is True
    assert any(path.endswith("design.md") for path in result["updated_files"])
    assert any(path.endswith("tasks.md") for path in result["updated_files"])
    assert not any("requirements.md" in path for path in result["updated_files"])


def test_quality_cycle_updates_requirements_from_saved_file(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key", max_iterations=1)
    runner = SpecificationWorkflowRunner(config=config)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    requirements_path = output_dir / "requirements.md"
    requirements_path.write_text("# Requirements\n- 기존 내용\n", encoding="utf-8")

    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "output_dir": str(output_dir),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
        "frs_content": "샘플 FRS",
    }

    quality_response = {
        "overall": 78,
        "needs_improvement": True,
        "feedback": [
            {"document": "requirements", "note": "보안 이벤트 로깅 요구사항을 추가하세요."}
        ],
    }
    consistency_response = {"issues": []}
    coordinator_response = {
        "approved": False,
        "required_improvements": [
            {"document": "requirements", "note": "감사 추적 흐름을 명시하세요."}
        ],
    }

    captured_prompts: List[str] = []

    def requirements_agent(prompt: str) -> str:
        captured_prompts.append(prompt)
        return "# Requirements\n- 업데이트된 내용\n"

    runner.agents = {
        "requirements": requirements_agent,
        "design": lambda prompt: "# Design\n",
        "tasks": lambda prompt: "# Tasks\n",
        "changes": lambda prompt: "# Changes\n",
        "openapi": lambda prompt: "{}",
        "quality_assessor": lambda prompt: json.dumps(quality_response, ensure_ascii=False),
        "consistency_checker": lambda prompt: json.dumps(
            consistency_response, ensure_ascii=False
        ),
        "coordinator": lambda prompt: json.dumps(
            coordinator_response, ensure_ascii=False
        ),
    }

    def fake_validate(agent_name, content):
        runner.context.documents.previous_contents[agent_name] = content
        runner.context.documents.template_results[agent_name] = {"success": True}
        return {"success": True}

    runner._validate_and_record_template = fake_validate

    def fake_save(agent_name, content):
        path = output_dir / (
            "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        )
        path.write_text(content, encoding="utf-8")
        return {
            "filename": path.name,
            "file_path": str(path),
            "size": len(content),
            "action": "test",
        }

    runner._save_document = fake_save

    quality_phase, feedback_phase = build_quality_phase(runner)

    result = asyncio.run(quality_phase.execute(ServiceType.API, feedback_phase))

    assert result["improvement_applied"] is True
    assert any(path.endswith("requirements.md") for path in result["updated_files"])
    assert requirements_path.read_text(encoding="utf-8") == "# Requirements\n- 업데이트된 내용\n"
    assert captured_prompts


def test_quality_cycle_saves_updates_in_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config = Config(openai_api_key="test-key", max_iterations=1)
    runner = SpecificationWorkflowRunner(config=config)

    requirements_path = tmp_path / "requirements.md"
    requirements_path.write_text("# Requirements\n- 기존 내용\n", encoding="utf-8")

    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "output_dir": str(tmp_path),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
        "frs_content": "샘플 FRS",
    }

    quality_response = {
        "overall": 78,
        "needs_improvement": True,
        "feedback": [
            {
                "document": "requirements",
                "note": "비밀번호 최소 길이와 복잡성 조건을 문서에 추가하세요.",
            }
        ],
    }
    consistency_response = {"issues": []}
    coordinator_response = {
        "approved": False,
        "required_improvements": [
            {
                "document": "requirements",
                "note": "변경 이력에 최신 버전 정보를 포함하세요.",
            }
        ],
    }

    captured_prompts: List[str] = []

    def requirements_agent(prompt: str) -> str:
        captured_prompts.append(prompt)
        return (
            "# Requirements\n"
            "- 비밀번호 최소 길이 12자 및 복잡성 조건 추가\n"
            "- 변경 이력에 1.1 버전 추가\n"
        )

    runner.agents = {
        "requirements": requirements_agent,
        "design": lambda prompt: "# Design\n",
        "tasks": lambda prompt: "# Tasks\n",
        "changes": lambda prompt: "# Changes\n",
        "openapi": lambda prompt: "{}",
        "quality_assessor": lambda prompt: json.dumps(quality_response, ensure_ascii=False),
        "consistency_checker": lambda prompt: json.dumps(
            consistency_response, ensure_ascii=False
        ),
        "coordinator": lambda prompt: json.dumps(
            coordinator_response, ensure_ascii=False
        ),
    }

    def fake_validate(agent_name, content):
        runner.context.documents.previous_contents[agent_name] = content
        runner.context.documents.template_results[agent_name] = {"success": True}
        return {"success": True}

    runner._validate_and_record_template = fake_validate

    def fake_save(agent_name, content):
        path = tmp_path / (
            "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        )
        path.write_text(content, encoding="utf-8")
        return {
            "filename": path.name,
            "file_path": str(path),
            "size": len(content),
            "action": "test",
        }

    runner._save_document = fake_save

    quality_phase, feedback_phase = build_quality_phase(runner)

    result = asyncio.run(quality_phase.execute(ServiceType.API, feedback_phase))

    assert result["improvement_applied"] is True
    assert str(requirements_path) in result["updated_files"]
    saved = requirements_path.read_text(encoding="utf-8")
    assert "비밀번호 최소 길이 12자" in saved
    assert "1.1 버전 추가" in saved
    assert captured_prompts


def test_quality_cycle_retries_unresolved_feedback(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key", max_iterations=2)
    runner = SpecificationWorkflowRunner(config=config)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    requirements_path = output_dir / "requirements.md"
    requirements_path.write_text("# Requirements\n- 기존 내용\n", encoding="utf-8")

    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "output_dir": str(output_dir),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
        "frs_content": "샘플 FRS",
    }

    quality_note = "REQ-001: 비밀번호 복잡성 요구사항을 명확히 작성하세요."
    quality_payloads = iter(
        [
            json.dumps(
                {
                    "overall": 70,
                    "needs_improvement": True,
                    "feedback": [{"document": "requirements", "note": quality_note}],
                    "completeness": 60,
                    "consistency": 60,
                    "clarity": 60,
                    "technical": 60,
                },
                ensure_ascii=False,
            )
            for _ in range(2)
        ]
    )

    consistency_payloads = iter(
        [
            json.dumps(
                {
                    "issues": [],
                    "severity": "low",
                    "cross_references": 0,
                    "naming_conflicts": 0,
                },
                ensure_ascii=False,
            )
            for _ in range(2)
        ]
    )

    coordinator_payloads = iter(
        [
            json.dumps(
                {
                    "approved": False,
                    "overall_quality": 70,
                    "decision": "개선필요",
                    "required_improvements": [],
                },
                ensure_ascii=False,
            )
            for _ in range(2)
        ]
    )

    def quality_agent(prompt: str) -> str:
        return next(quality_payloads)

    def consistency_agent(prompt: str) -> str:
        return next(consistency_payloads)

    def coordinator_agent(prompt: str) -> str:
        return next(coordinator_payloads)

    requirements_calls = 0

    def requirements_agent(prompt: str) -> str:
        nonlocal requirements_calls
        requirements_calls += 1
        return (
            "# Requirements\n"
            "- 기존 내용\n"
            "- 비밀번호는 최소 10자 이상, 대문자/소문자/숫자/특수문자를 포함해야 합니다.\n"
        )

    runner.agents = {
        "requirements": requirements_agent,
        "design": lambda prompt: "# Design\n",
        "tasks": lambda prompt: "# Tasks\n",
        "changes": lambda prompt: "# Changes\n",
        "openapi": lambda prompt: "{}",
        "quality_assessor": quality_agent,
        "consistency_checker": consistency_agent,
        "coordinator": coordinator_agent,
    }

    def fake_validate(agent_name, content):
        runner.context.documents.previous_contents[agent_name] = content
        runner.context.documents.template_results[agent_name] = {"success": True}
        return {"success": True}

    runner._validate_and_record_template = fake_validate

    def fake_save(agent_name, content):
        path = output_dir / (
            "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        )
        path.write_text(content, encoding="utf-8")
        return {
            "filename": path.name,
            "file_path": str(path),
            "size": len(content),
            "action": "test",
        }

    runner._save_document = fake_save

    quality_phase, feedback_phase = build_quality_phase(runner)

    result = asyncio.run(quality_phase.execute(ServiceType.API, feedback_phase))

    assert result["improvement_applied"] is True
    assert requirements_calls >= 1
    store = runner.context.quality.get("applied_feedback", {}).get("requirements", [])
    assert any(
        isinstance(entry, dict)
        and entry.get("status") == "pending"
        and "비밀번호 복잡성" in entry.get("note", "")
        for entry in store
    )
    saved_content = requirements_path.read_text(encoding="utf-8")
    assert "비밀번호는 최소 10자 이상" in saved_content


def test_quality_cycle_marks_feedback_verified_once_resolved(tmp_path, monkeypatch):
    config = Config(openai_api_key="test-key", max_iterations=2)
    runner = SpecificationWorkflowRunner(config=config)

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    requirements_path = output_dir / "requirements.md"
    requirements_path.write_text("# Requirements\n- 기존 내용\n", encoding="utf-8")

    runner.context.project = {
        "frs_path": str(tmp_path / "FRS-SAMPLE.md"),
        "output_dir": str(output_dir),
        "frs_id": "FRS-TEST",
        "service_type": ServiceType.API.value,
        "frs_content": "샘플 FRS",
    }

    quality_payloads = iter(
        [
            json.dumps(
                {
                    "overall": 70,
                    "needs_improvement": True,
                    "feedback": [
                        {"document": "requirements", "note": "REQ-001: 비밀번호 정책을 명시하세요."}
                    ],
                    "completeness": 60,
                    "consistency": 60,
                    "clarity": 60,
                    "technical": 60,
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "overall": 85,
                    "needs_improvement": False,
                    "feedback": [],
                    "completeness": 80,
                    "consistency": 82,
                    "clarity": 84,
                    "technical": 86,
                },
                ensure_ascii=False,
            ),
        ]
    )

    consistency_payloads = iter(
        [
            json.dumps(
                {
                    "issues": [],
                    "severity": "low",
                    "cross_references": 0,
                    "naming_conflicts": 0,
                },
                ensure_ascii=False,
            )
            for _ in range(2)
        ]
    )

    coordinator_payloads = iter(
        [
            json.dumps(
                {
                    "approved": False,
                    "overall_quality": 70,
                    "decision": "개선필요",
                    "required_improvements": [],
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "approved": True,
                    "overall_quality": 85,
                    "decision": "승인",
                    "required_improvements": [],
                },
                ensure_ascii=False,
            ),
        ]
    )

    requirements_calls = 0

    def requirements_agent(prompt: str) -> str:
        nonlocal requirements_calls
        requirements_calls += 1
        return (
            "# Requirements\n"
            "- 기존 내용\n"
            "- 비밀번호 정책: 최소 12자, 대문자/소문자/숫자/특수문자 포함.\n"
        )

    runner.agents = {
        "requirements": requirements_agent,
        "design": lambda prompt: "# Design\n",
        "tasks": lambda prompt: "# Tasks\n",
        "changes": lambda prompt: "# Changes\n",
        "openapi": lambda prompt: "{}",
        "quality_assessor": lambda prompt: next(quality_payloads),
        "consistency_checker": lambda prompt: next(consistency_payloads),
        "coordinator": lambda prompt: next(coordinator_payloads),
    }

    def fake_validate(agent_name, content):
        runner.context.documents.previous_contents[agent_name] = content
        runner.context.documents.template_results[agent_name] = {"success": True}
        return {"success": True}

    runner._validate_and_record_template = fake_validate

    def fake_save(agent_name, content):
        path = output_dir / (
            "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        )
        path.write_text(content, encoding="utf-8")
        return {
            "filename": path.name,
            "file_path": str(path),
            "size": len(content),
            "action": "test",
        }

    runner._save_document = fake_save

    quality_phase, feedback_phase = build_quality_phase(runner)

    result = asyncio.run(quality_phase.execute(ServiceType.API, feedback_phase))

    assert result["improvement_applied"] is True
    assert requirements_calls == 1
    store = runner.context.quality.get("applied_feedback", {})
    verified_entries = [
        entry
        for entry in store.get("requirements", [])
        if isinstance(entry, dict) and entry.get("status") == "verified"
    ]
    assert verified_entries
    assert any("비밀번호 정책" in entry.get("note", "") for entry in verified_entries)
    saved_content = requirements_path.read_text(encoding="utf-8")
    assert "비밀번호 정책" in saved_content
