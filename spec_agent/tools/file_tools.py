"""파일 I/O 및 디렉터리 관리 도구들."""

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
    생성된 명세서를 위한 출력 디렉토리 구조를 생성합니다.

    Args:
        base_path: 기본 디렉토리 경로 (예: "specs")
        frs_id: FRS 식별자 (예: "FRS-1")
        service_type: 서비스 타입 ("api" 또는 "web")

    Returns:
        디렉토리 생성 결과를 담은 딕셔너리
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
    명세서 컨텐츠를 파일로 작성합니다 (비동기 버전).

    Args:
        directory_path: 파일을 작성할 디렉토리 경로
        content: 작성할 컨텐츠
        filename: 파일명

    Returns:
        쓰기 작업 결과를 담은 딕셔너리
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
    명세서 파일 컨텐츠를 읽습니다.

    Args:
        file_path: 파일의 전체 경로

    Returns:
        파일 컨텐츠와 메타데이터를 담은 딕셔너리
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
    디렉토리의 모든 명세서 파일을 나열합니다.

    Args:
        directory_path: 디렉토리 경로

    Returns:
        파일 목록을 담은 딕셔너리
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
