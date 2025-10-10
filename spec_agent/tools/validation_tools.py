"""Validation tools for generated specifications."""

import json
import re
from typing import Dict, Any, List
from jsonschema import validate, ValidationError
from strands import tool


@tool
def validate_openapi_spec(openapi_content: str) -> Dict[str, Any]:
    """
    Validate OpenAPI 3.1 specification.

    Args:
        openapi_content: JSON string containing OpenAPI specification

    Returns:
        Dictionary with validation results
    """
    try:
        # Parse JSON
        try:
            spec = json.loads(openapi_content)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {str(e)}"}

        # Basic OpenAPI 3.1 schema validation
        required_fields = ["openapi", "info", "paths"]
        missing_fields = []

        for field in required_fields:
            if field not in spec:
                missing_fields.append(field)

        if missing_fields:
            return {
                "success": False,
                "error": f"Missing required fields: {missing_fields}",
            }

        # Check OpenAPI version
        openapi_version = spec.get("openapi", "")
        if not openapi_version.startswith("3.1"):
            return {
                "success": False,
                "error": f"Expected OpenAPI 3.1.x, got: {openapi_version}",
            }

        # Validate info section
        info = spec.get("info", {})
        if not info.get("title") or not info.get("version"):
            return {
                "success": False,
                "error": "Info section must contain title and version",
            }

        # Count API elements
        paths_count = len(spec.get("paths", {}))
        components_count = len(spec.get("components", {}).get("schemas", {}))

        return {
            "success": True,
            "openapi_version": openapi_version,
            "api_title": info.get("title"),
            "api_version": info.get("version"),
            "paths_count": paths_count,
            "components_count": components_count,
            "validation_summary": f"Valid OpenAPI 3.1 spec with {paths_count} paths and {components_count} components",
        }

    except Exception as e:
        return {"success": False, "error": f"OpenAPI validation failed: {str(e)}"}


@tool
def validate_markdown_content(content: str, document_type: str) -> Dict[str, Any]:
    """
    Validate markdown content structure and quality.

    Args:
        content: Markdown content to validate
        document_type: Type of document (requirements, design, tasks, changes)

    Returns:
        Dictionary with validation results
    """
    try:
        issues = []
        warnings = []
        metrics = {}

        # Basic content checks
        if not content.strip():
            issues.append("Document is empty")
            return {
                "success": False,
                "issues": issues,
                "warnings": warnings,
                "metrics": metrics,
            }

        # Check for proper heading structure
        headings = re.findall(r"^(#{1,6})\s+(.+)$", content, re.MULTILINE)
        if not headings:
            issues.append("No headings found")
        else:
            # Check heading hierarchy
            prev_level = 0
            for heading_marks, heading_text in headings:
                current_level = len(heading_marks)
                if current_level > prev_level + 1:
                    warnings.append(f"Heading level jump: '{heading_text}'")
                prev_level = current_level

        # Document type specific validations
        if document_type == "requirements":
            # Check for requirements identifiers
            req_ids = re.findall(r"REQ-\d+", content)
            if not req_ids:
                warnings.append("No requirement identifiers (REQ-XXX) found")
            metrics["requirements_count"] = len(req_ids)

        elif document_type == "design":
            # Check for sequence diagrams
            if (
                "mermaid" not in content.lower()
                and "sequencediagram" not in content.lower()
            ):
                warnings.append("No sequence diagram found")

        elif document_type == "tasks":
            # Check for task tables
            table_count = len(re.findall(r"\|.*\|", content))
            if table_count < 3:  # Header + separator + at least one row
                warnings.append("Task tables appear to be missing or incomplete")
            metrics["table_rows"] = table_count

        elif document_type == "changes":
            # Check for version information
            if not re.search(r"version|v\d+\.\d+", content, re.IGNORECASE):
                warnings.append("No version information found")

        # General quality checks
        word_count = len(content.split())
        line_count = len(content.splitlines())

        if word_count < 100:
            warnings.append(f"Document seems short ({word_count} words)")

        # Check for TODO/FIXME markers
        todo_markers = re.findall(r"TODO|FIXME|TBD|XXX", content, re.IGNORECASE)
        if todo_markers:
            warnings.append(f"Found {len(todo_markers)} TODO/FIXME markers")

        metrics.update(
            {
                "word_count": word_count,
                "line_count": line_count,
                "heading_count": len(headings),
                "todo_count": len(todo_markers),
            }
        )

        return {
            "success": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "metrics": metrics,
            "document_type": document_type,
        }

    except Exception as e:
        return {"success": False, "error": f"Markdown validation failed: {str(e)}"}


@tool
def generate_validation_report(
    validation_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Generate a comprehensive validation report from multiple validation results.

    Args:
        validation_results: List of validation result dictionaries

    Returns:
        Dictionary with consolidated validation report
    """
    try:
        total_files = len(validation_results)
        successful_files = sum(
            1 for result in validation_results if result.get("success", False)
        )
        failed_files = total_files - successful_files

        all_issues = []
        all_warnings = []

        for result in validation_results:
            if "issues" in result:
                all_issues.extend(result["issues"])
            if "warnings" in result:
                all_warnings.extend(result["warnings"])

        overall_success = failed_files == 0

        summary = f"Validation completed: {successful_files}/{total_files} files passed"
        if all_issues:
            summary += f", {len(all_issues)} issues found"
        if all_warnings:
            summary += f", {len(all_warnings)} warnings"

        return {
            "success": overall_success,
            "summary": summary,
            "total_files": total_files,
            "successful_files": successful_files,
            "failed_files": failed_files,
            "total_issues": len(all_issues),
            "total_warnings": len(all_warnings),
            "issues": all_issues,
            "warnings": all_warnings,
            "details": validation_results,
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to generate validation report: {str(e)}",
        }
