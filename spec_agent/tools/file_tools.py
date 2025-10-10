"""File I/O and directory management tools."""

import json
import aiofiles
from pathlib import Path
from typing import Dict, Any
from strands import tool


@tool
def create_output_directory(
    base_path: str, frs_id: str, service_type: str
) -> Dict[str, Any]:
    """
    Create output directory structure for generated specifications.

    Args:
        base_path: Base directory path (e.g., "specs")
        frs_id: FRS identifier (e.g., "FRS-1")
        service_type: Service type ("api" or "web")

    Returns:
        Dictionary with directory creation results
    """
    try:
        output_dir = Path(base_path) / frs_id / service_type
        output_dir.mkdir(parents=True, exist_ok=True)

        return {"success": True, "output_dir": str(output_dir), "created": True}

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to create output directory: {str(e)}",
        }



@tool
async def write_spec_file(
    directory_path: str, content: str, filename: str
) -> Dict[str, Any]:
    """
    Write specification content to file (async version).

    Args:
        directory_path: Directory path where file should be written
        content: Content to write
        filename: Name of the file

    Returns:
        Dictionary with write operation results
    """
    try:
        output_path = Path(directory_path) / filename

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content based on file type
        if filename.endswith(".json"):
            # Parse and pretty-print JSON
            try:
                json_data = json.loads(content)
                formatted_content = json.dumps(json_data, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                formatted_content = content
        else:
            formatted_content = content

        async with aiofiles.open(output_path, "w", encoding="utf-8") as f:
            await f.write(formatted_content)

        return {
            "success": True,
            "file_path": str(output_path),
            "filename": filename,
            "size": len(formatted_content),
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to write file {filename}: {str(e)}"}


@tool
async def read_spec_file(file_path: str) -> Dict[str, Any]:
    """
    Read specification file content.

    Args:
        file_path: Full path to the file

    Returns:
        Dictionary with file content and metadata
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}

        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()

        return {
            "success": True,
            "content": content,
            "file_path": str(path),
            "filename": path.name,
            "size": len(content),
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to read file {file_path}: {str(e)}"}


@tool
def list_spec_files(directory_path: str) -> Dict[str, Any]:
    """
    List all specification files in a directory.

    Args:
        directory_path: Path to the directory

    Returns:
        Dictionary with file listing
    """
    try:
        path = Path(directory_path)
        if not path.exists():
            return {"success": False, "error": f"Directory not found: {directory_path}"}

        spec_files = []
        for file_path in path.glob("*"):
            if file_path.is_file() and file_path.suffix in [".md", ".json"]:
                spec_files.append(
                    {
                        "filename": file_path.name,
                        "path": str(file_path),
                        "size": file_path.stat().st_size,
                        "type": file_path.suffix[1:],  # Remove the dot
                    }
                )

        return {
            "success": True,
            "directory": str(path),
            "files": spec_files,
            "count": len(spec_files),
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to list files in {directory_path}: {str(e)}",
        }
