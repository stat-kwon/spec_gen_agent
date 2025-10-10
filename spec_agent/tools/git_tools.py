"""Git workflow management tools."""

import subprocess
import re
from pathlib import Path
from typing import Dict, Any
from strands import tool


@tool
def create_git_branch(
    frs_id: str, service_type: str, base_branch: str = "main"
) -> Dict[str, Any]:
    """
    Create a git branch following the naming convention.

    Args:
        frs_id: FRS identifier (e.g., "FRS-1")
        service_type: Service type ("api" or "web")
        base_branch: Base branch to create from (default: "main")

    Returns:
        Dictionary with branch creation results
    """
    try:
        # Generate branch name following convention: specgen/scenario-3/<frs-id>-<service>
        branch_name = f"specgen/scenario-3/{frs_id.lower()}-{service_type}"

        # Check if branch already exists
        result = subprocess.run(
            ["git", "branch", "--list", branch_name], capture_output=True, text=True
        )

        if result.stdout.strip():
            # Branch exists, switch to it
            subprocess.run(["git", "checkout", branch_name], check=True)
            return {
                "success": True,
                "branch_name": branch_name,
                "action": "switched_to_existing",
                "message": f"Switched to existing branch: {branch_name}",
            }
        else:
            # Create new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name, base_branch], check=True
            )
            return {
                "success": True,
                "branch_name": branch_name,
                "action": "created_new",
                "message": f"Created new branch: {branch_name}",
            }

    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Git branch operation failed: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Branch creation failed: {str(e)}"}


@tool
def commit_changes(
    frs_id: str, service_type: str, files_written: list
) -> Dict[str, Any]:
    """
    Commit generated specification files following the commit message convention.

    Args:
        frs_id: FRS identifier (e.g., "FRS-1")
        service_type: Service type ("api" or "web")
        files_written: List of file paths that were written

    Returns:
        Dictionary with commit results
    """
    try:
        if not files_written:
            return {"success": False, "error": "No files to commit"}

        # Add files to git
        for file_path in files_written:
            subprocess.run(["git", "add", file_path], check=True)

        # Generate commit message following convention: spec(#frs-n): add <service> spec docs
        frs_number = re.search(r"(\d+)", frs_id)
        frs_num = frs_number.group(1) if frs_number else "unknown"

        commit_message = f"""spec(#{frs_id.lower()}): add {service_type} spec docs

Generated specification documents:
{chr(10).join(f"- {Path(f).name}" for f in files_written)}"""

        # Commit changes
        subprocess.run(["git", "commit", "-m", commit_message], check=True)

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        commit_hash = result.stdout.strip()

        return {
            "success": True,
            "commit_hash": commit_hash,
            "commit_message": commit_message,
            "files_committed": files_written,
            "message": f"Committed {len(files_written)} files",
        }

    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Git commit failed: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Commit operation failed: {str(e)}"}


@tool
def get_git_status() -> Dict[str, Any]:
    """
    Get current git repository status.

    Returns:
        Dictionary with git status information
    """
    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_branch = branch_result.stdout.strip()

        # Get status
        status_result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        )

        # Parse status output
        modified_files = []
        untracked_files = []

        for line in status_result.stdout.splitlines():
            if line.startswith("??"):
                untracked_files.append(line[3:])
            elif line.startswith(" M") or line.startswith("M "):
                modified_files.append(line[3:])

        return {
            "success": True,
            "current_branch": current_branch,
            "modified_files": modified_files,
            "untracked_files": untracked_files,
            "has_changes": bool(modified_files or untracked_files),
        }

    except subprocess.CalledProcessError as e:
        return {"success": False, "error": f"Git status check failed: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Git status operation failed: {str(e)}"}
