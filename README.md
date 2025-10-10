# Optimized Agentic Loop Spec Generator

Advanced AI-powered specification generator using iterative refinement for high-quality service documentation from FRS (Functional Requirements Specification) files. Features token optimization, incremental saving, and quality-driven document generation.

## Features

- Generates complete specification packages from FRS markdown files
- Supports both API and Web service types
- Creates standardized documentation:
  - `requirements.md` - Requirements documentation
  - `design.md` - Design documentation with architecture diagrams
  - `tasks.md` - Work breakdown structure with Epic/Story/Task hierarchy
  - `changes.md` - Change management documentation
  - `apis.json` - OpenAPI 3.1 specification (API services only)
- Built-in validation and quality checks
- Agent-based architecture for modular processing

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd spec-agent

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .
```

## Configuration

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Configure your OpenAI API credentials:
```
OPENAI_API_KEY=your-api-key-here
```

## Usage

### Generate Specifications

```bash
# Generate API service specifications
spec-agent generate specs/FRS-1.md --service-type api

# Generate Web service specifications  
spec-agent generate specs/FRS-1.md --service-type web

# Specify custom output directory
spec-agent generate specs/FRS-1.md --service-type api --output-dir ./output

# Skip validation checks
spec-agent generate specs/FRS-1.md --service-type api --no-validate
```

### Validate Existing Specifications

```bash
# Validate specification documents
spec-agent validate specs/FRS-1/api
```

### Show Version

```bash
spec-agent version
```

## Project Structure

```
spec-agent/
├── spec_agent/
│   ├── agents/          # Agent implementations
│   │   ├── base.py      # Base agent class
│   │   ├── frs_loader.py
│   │   ├── reqs_agent.py
│   │   ├── design_agent.py
│   │   ├── tasks_agent.py
│   │   ├── changes_agent.py
│   │   ├── openapi_agent.py
│   │   ├── qc_inspector.py
│   │   └── repo_writer.py
│   ├── models.py        # Data models
│   ├── orchestrator.py  # Main orchestration logic
│   └── cli.py          # CLI interface
├── specs/              # FRS files and generated specs
├── tests/              # Test files
└── requirements.txt    # Dependencies
```

## Output Structure

Generated specifications are organized as follows:

```
specs/
└── FRS-1/
    ├── api/
    │   ├── requirements.md
    │   ├── design.md
    │   ├── tasks.md
    │   ├── changes.md
    │   └── apis.json
    └── web/
        ├── requirements.md
        ├── design.md
        ├── tasks.md
        └── changes.md
```

## Development

```bash
# Run in development mode
python -m spec_agent generate specs/FRS-1.md --service-type api

# Run tests
pytest tests/
```

## License

MIT