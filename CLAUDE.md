# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **LLM-powered specification generation agent system** that automates the creation of service documentation from FRS (Functional Requirements Specification) markdown files. The system uses OpenAI GPT models through a sequential agent workflow to generate comprehensive documentation packages.

## Development Status

**Current Phase**: LLM-powered implementation complete
- Fully functional LLM-based agent system
- Sequential flow: FRS → requirements → design → tasks → changes → apis
- Python 3.9+ runtime with OpenAI integration
- Ready for production use with proper API key configuration

## Architecture

### Input/Output Flow
- **Input**: FRS markdown files located at `specs/FRS-n.md`
- **Output**: Service documentation packages at `specs/FRS-n/{api|web}/`
  - `requirements.md` - Requirements documentation
  - `design.md` - Design documentation with sequence diagrams
  - `tasks.md` - Work breakdown structure
  - `changes.md` - Change management documentation
  - `apis.json` - OpenAPI 3.1 specification (API services only)

### LLM Agent System (Implementation)
The system uses LLM-powered agents in sequential flow:
1. **FRSLoader** - Loads and parses FRS markdown files
2. **LLMReqsAgent** - Generates requirements.md using GPT-4
3. **LLMDesignAgent** - Creates design.md with architecture diagrams
4. **LLMTasksAgent** - Generates Epic/Story/Task breakdown
5. **LLMChangesAgent** - Creates change management documentation  
6. **LLMOpenAPIAgent** - Generates OpenAPI 3.1 specifications
7. **QCInspector** - Validates generated documents
8. **RepoWriter** - Handles file operations and Git workflow

### Key Technologies (Current)
- **AI Models**: OpenAI GPT-4 (configurable)
- **Framework**: Custom LLM orchestration with async execution
- **Dependencies**: `openai>=1.0.0`, `pydantic>=2.0.0`, `click>=8.1.0`

## Development Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your OPENAI_API_KEY
```

### Running the LLM System
```bash
# Generate API service specifications
python -m spec_agent generate specs/FRS-1.md --service-type api

# Generate Web service specifications  
python -m spec_agent generate specs/FRS-1.md --service-type web

# Validate existing specifications
python -m spec_agent validate specs/FRS-1/api

# Show setup instructions
python -m spec_agent setup
```

### Development workflow
```bash
# Test with sample FRS
python -m spec_agent generate specs/FRS-1.md --service-type api

# Quality checks
python -m spec_agent validate specs/FRS-1/api
```

## Git Workflow

Branch naming convention:
```
specgen/scenario-3/<frs-id>-<service>
```

Commit message format:
```
spec(#frs-n): add <service> spec docs
```

## Document Templates

The system enforces specific document templates:

### requirements.md Structure
- Header/Meta → Scope → Functional Requirements → Error Requirements → Security & Privacy → Observability → Acceptance Criteria

### design.md Structure
- Architecture → Sequence Diagram → Data Model → API Contract → Security & Permissions → Performance Goals

### tasks.md Structure
- Epic/Story/Task tables with DoD checklist

### changes.md Structure
- Version History → Change Summary → Impact/Risk → Rollback Plan → Known Issues

### apis.json
- OpenAPI 3.1 specification with standard sections

## Important Implementation Notes

1. **No RAG Dependencies**: The system avoids external dependencies like glossaries or Apidog
2. **Deterministic Generation**: Use rule-based and template-driven document generation
3. **Quality Gates**: All generated markdown must be valid, OpenAPI specs must pass schema validation
4. **Service Types**: Support both 'api' and 'web' service types with appropriate documentation sets

## Next Steps for Implementation

When implementing this system:
1. Initialize Git repository
2. Create Python package structure (src/, tests/, docs/)
3. Set up dependency management (requirements.txt or pyproject.toml)
4. Implement the agent framework integration
5. Create the document generation templates
6. Add validation and quality gate tooling