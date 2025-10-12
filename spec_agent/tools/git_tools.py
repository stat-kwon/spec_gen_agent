"""Git 워크플로우 관리 도구들."""

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
    명명 규칙에 따라 Git 브랜치를 생성합니다.

    Args:
        frs_id: FRS 식별자 (예: "FRS-1")
        service_type: 서비스 타입 ("api" 또는 "web")
        base_branch: 기준 브랜치 (기본값: "main")

    Returns:
        브랜치 생성 결과를 담은 딕셔너리
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
    커밋 메시지 규칙에 따라 생성된 명세서 파일들을 커밋합니다.

    Args:
        frs_id: FRS 식별자 (예: "FRS-1")
        service_type: 서비스 타입 ("api" 또는 "web")
        files_written: 작성된 파일 경로 목록

    Returns:
        커밋 결과를 담은 딕셔너리
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
    현재 Git 저장소의 상태를 가져옵니다.

    Returns:
        Git 상태 정보를 담은 딕셔너리
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
