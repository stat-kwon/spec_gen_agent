"""
Command-line interface for the Strands Agent SDK based spec_agent system.
"""

import sys
from pathlib import Path
from typing import Optional

import click
from .config import Config
from .models import ServiceType
from .workflow import SpecificationWorkflow


@click.group()
@click.version_option(version="2.0.0")
@click.pass_context
def cli(ctx):
    """
    Strands Agent SDK 기반 명세서 생성기.

    Strands Agent SDK로 구동되는 멀티 에이전트 시스템을 사용하여
    FRS 파일로부터 포괄적인 서비스 문서를 생성합니다.
    """
    ctx.ensure_object(dict)

    # Initialize configuration
    try:
        config = Config.from_env()
        config.validate()
        ctx.obj["config"] = config
    except Exception as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("frs_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--service-type",
    type=click.Choice(["api", "web"], case_sensitive=False),
    required=True,
    help="Type of service to generate specifications for",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    help="Custom output directory (default: specs/FRS-N/service-type)",
)
@click.option(
    "--no-validate", is_flag=True, help="Skip validation of generated documents"
)
@click.option(
    "--no-git", is_flag=True, help="Skip git workflow (branch creation and commit)"
)
@click.pass_context
def generate(
    ctx,
    frs_path: Path,
    service_type: str,
    output_dir: Optional[Path],
    no_validate: bool,
    no_git: bool,
):
    """
    FRS 파일로부터 명세서 문서를 생성합니다.

    예제:
        spec_agent generate specs/FRS-1.md --service-type api
        spec_agent generate specs/FRS-2.md --service-type web --output-dir custom/output
    """
    config = ctx.obj["config"]

    # Validate input
    if not frs_path.exists():
        click.echo(f"❌ FRS file not found: {frs_path}", err=True)
        sys.exit(1)

    # Convert service type
    try:
        service_enum = ServiceType(service_type.lower())
    except ValueError:
        click.echo(f"❌ Invalid service type: {service_type}", err=True)
        sys.exit(1)

    # Strands Agent SDK 워크플로우 사용
    click.echo(f"🌟 Using Strands Agent SDK native workflow patterns")
    workflow = SpecificationWorkflow(config)

    # Run generation
    click.echo(f"🚀 Starting specification generation...")
    click.echo(f"📖 FRS: {frs_path}")
    click.echo(f"🔧 Service Type: {service_enum.value}")

    try:
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Strands 네이티브 워크플로우 실행
            result = loop.run_until_complete(
                workflow.execute_workflow(
                    frs_path=str(frs_path),
                    service_type=service_enum,
                    output_dir=str(output_dir) if output_dir else None,
                    use_git=not no_git,
                )
            )
        finally:
            loop.close()

        if result["success"]:
            click.echo(f"\n✅ Specification generation completed successfully!")
            click.echo(f"📁 Output directory: {result['output_dir']}")
            click.echo(f"📄 Files generated: {len(result['files_written'])}")

            for file_path in result["files_written"]:
                click.echo(f"  ✅ {Path(file_path).name}")

            # Show execution metrics
            if result.get("quality_results"):
                # Strands 워크플로우 메트릭
                click.echo(f"\n📊 Strands Workflow Metrics:")
                click.echo(f"  • Framework: {result.get('framework', 'Strands Agent SDK')}")
                click.echo(f"  • Pattern: {result.get('pattern', 'Agent-to-Agent')}")
                
                if 'execution_time' in result:
                    click.echo(f"  • Execution Time: {result['execution_time']:.1f}s")
                
                
                # 품질 결과 표시
                quality_results = result["quality_results"]
                avg_quality = sum(r.get('overall', 0) for r in quality_results.values()) / len(quality_results)
                click.echo(f"  • Average Quality: {avg_quality:.1f}%")
                
                click.echo(f"\n📈 Document Quality Scores:")
                for doc_type, scores in quality_results.items():
                    overall = scores.get("overall", 0)
                    status = "✅" if overall >= 70 else "⚠️" if overall >= 50 else "❌"
                    click.echo(f"  {status} {doc_type}: {overall:.1f}%")
                    
                # 일관성 결과 표시
                if result.get("consistency_results"):
                    consistency = result["consistency_results"]
                    total_issues = sum(len(issues) for issues in consistency.values())
                    click.echo(f"\n🔍 Consistency Check:")
                    click.echo(f"  • Total Issues: {total_issues}")
                    
            elif result.get("quality_report"):
                # 레거시 메트릭 (하위 호환성)
                report = result["quality_report"]
                click.echo(f"\n📊 Performance Metrics:")
                click.echo(
                    f"  • Average Quality: {report.get('average_quality', 0):.1f}%"
                )
                click.echo(f"  • Iterations Used: {result.get('iterations', 0)}")
                click.echo(
                    f"  • Converged: {'Yes' if result.get('converged') else 'No'}"
                )

                if report.get("quality_breakdown"):
                    click.echo(f"\n📈 Document Quality Scores:")
                    for doc_type, scores in report["quality_breakdown"].items():
                        overall = scores.get("overall", 0)
                        status = (
                            "✅" if overall >= 70 else "⚠️" if overall >= 50 else "❌"
                        )
                        click.echo(f"  {status} {doc_type}: {overall:.1f}%")

                # Show time efficiency if available
                if "total_time" in result:
                    click.echo(f"\n⏱️ Time Efficiency:")
                    click.echo(f"  • Total Time: {result['total_time']:.1f}s")
                    click.echo(
                        f"  • Time per Document: {result['total_time']/len(result['files_written']):.1f}s"
                    )
                    if result.get("incremental_saves"):
                        click.echo(
                            f"  • Incremental Saves: {len(result['incremental_saves'])} saves"
                        )
            elif result.get("validation_results"):
                click.echo(f"\n🔍 Validation summary:")
                for validation in result["validation_results"]:
                    status = (
                        "✅"
                        if "success" in validation.get("result", "").lower()
                        else "⚠️"
                    )
                    click.echo(f"  {status} {validation['document']}")
        else:
            click.echo(
                f"❌ Generation failed: {result.get('error', 'Unknown error')}",
                err=True,
            )
            sys.exit(1)

    except KeyboardInterrupt:
        click.echo(f"\n⚠️ Generation interrupted by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"❌ Unexpected error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("spec_dir", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def validate(ctx, spec_dir: Path):
    """
    기존 명세서 문서를 검증합니다.

    예제:
        spec_agent validate specs/FRS-1/api
        spec_agent validate specs/FRS-2/web
    """
    config = ctx.obj["config"]

    if not spec_dir.is_dir():
        click.echo(f"❌ Not a directory: {spec_dir}", err=True)
        sys.exit(1)

    # Initialize Strands workflow
    workflow = SpecificationWorkflow(config)

    click.echo(f"🔍 Validating specifications in: {spec_dir}")

    try:
        # Run validation using Strands workflow
        result = workflow.validate_existing_specs(str(spec_dir))

        if result["success"]:
            click.echo(f"\n✅ Validation completed!")

            if result.get("validation_results"):
                click.echo(f"📋 Validation summary:")
                for validation in result["validation_results"]:
                    status = (
                        "✅"
                        if "success" in validation.get("result", "").lower()
                        else "❌"
                    )
                    file_name = Path(validation["file_path"]).name
                    click.echo(f"  {status} {file_name}")

            # Show overall report if available
            if result.get("report"):
                click.echo(f"\n📊 Overall Report:")
                click.echo(f"  {result['report']}")
        else:
            click.echo(
                f"❌ Validation failed: {result.get('error', 'Unknown error')}",
                err=True,
            )
            sys.exit(1)

    except Exception as e:
        click.echo(f"❌ Validation error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def setup(ctx):
    """
    설치 안내 및 구성 정보를 표시합니다.
    """
    config = ctx.obj["config"]

    click.echo("🛠️  Strands Agent SDK Spec Generator Setup")
    click.echo("=" * 50)

    click.echo("\n📋 Prerequisites:")
    click.echo("  • Python 3.9+")
    click.echo("  • OpenAI API key")
    click.echo("  • Git (for workflow management)")

    click.echo("\n🔧 Configuration:")
    click.echo(f"  • OpenAI Model: {config.openai_model}")
    click.echo(f"  • Temperature: {config.openai_temperature}")
    click.echo(f"  • Default Output Dir: {config.default_output_dir}")
    click.echo(f"  • Git Branch Prefix: {config.git_branch_prefix}")

    # Check API key
    if config.openai_api_key:
        click.echo(f"  ✅ OpenAI API Key: Configured")
    else:
        click.echo(f"  ❌ OpenAI API Key: Missing")
        click.echo(f"\n⚠️  Please set OPENAI_API_KEY environment variable")

    click.echo("\n📖 Usage Examples:")
    click.echo("  # Generate API service specifications")
    click.echo("  spec_agent generate specs/FRS-1.md --service-type api")
    click.echo("")
    click.echo("  # Generate Web service specifications")
    click.echo("  spec_agent generate specs/FRS-2.md --service-type web")
    click.echo("")
    click.echo("  # Validate existing specifications")
    click.echo("  spec_agent validate specs/FRS-1/api")

    click.echo("\n🔗 More Information:")
    click.echo("  • Strands Agent SDK: https://strandsagents.com/")
    click.echo("  • OpenAI API: https://platform.openai.com/")


@cli.command()
@click.pass_context
def agents(ctx):
    """
    사용 가능한 에이전트와 그 기능을 나열합니다.
    """
    click.echo("🤖 Available Strands Agents")
    click.echo("=" * 40)

    agents_info = [
        ("requirements", "Generate requirements.md from FRS", "🎯"),
        ("design", "Generate design.md with architecture", "🏗️"),
        ("tasks", "Generate tasks.md with Epic/Story/Task breakdown", "📋"),
        ("changes", "Generate changes.md with deployment info", "📝"),
        ("openapi", "Generate apis.json OpenAPI 3.1 spec (API only)", "🔌"),
        ("validation", "Validate all generated documents", "🔍"),
    ]

    for agent_name, description, emoji in agents_info:
        click.echo(f"\n{emoji} {agent_name.title()} Agent")
        click.echo(f"   {description}")

    click.echo(f"\n🎭 Multi-Agent Coordination:")
    click.echo(f"   • Agents work together in sequence")
    click.echo(f"   • Context passed between agents")
    click.echo(f"   • Automatic error handling and retries")
    click.echo(f"   • Quality validation at each step")




if __name__ == "__main__":
    cli()
