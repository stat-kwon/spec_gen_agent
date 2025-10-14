"""파일 I/O 및 디렉터리 관리 도구들."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any

import aiofiles
from strands import tool

from spec_agent.utils.logging import get_session_logger


LOGGER = logging.getLogger("spec_agent.tools.file")


def _get_logger(
    session_id: str | None = None,
) -> logging.LoggerAdapter | logging.Logger:
    if session_id:
        return get_session_logger("tools.file", session_id)
    return LOGGER


@tool
async def read_spec_file(
    file_path: str,
    *,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    명세서 파일 컨텐츠를 읽습니다.

    Args:
        file_path: 파일의 전체 경로

    Returns:
        파일 컨텐츠와 메타데이터를 담은 딕셔너리
    """
    logger = _get_logger(session_id)
    logger.info("문서 읽기 시도 | 경로=%s", file_path)

    try:
        path = Path(file_path)
        if not path.exists():
            logger.warning("문서 읽기 실패 | 파일 없음")
            return {"success": False, "error": f"File not found: {file_path}"}

        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            content = await f.read()

        result = {
            "success": True,
            "content": content,
            "file_path": str(path),
            "filename": path.name,
            "size": len(content),
        }
        logger.info(
            "문서 읽기 완료 | 파일=%s | 크기=%d",
            result["filename"],
            result["size"],
        )
        return result

    except Exception as e:
        logger.exception("문서 읽기 실패")
        return {"success": False, "error": f"Failed to read file {file_path}: {str(e)}"}


@tool
def list_spec_files(
    directory_path: str,
    *,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """
    디렉토리의 모든 명세서 파일을 나열합니다.

    Args:
        directory_path: 디렉토리 경로

    Returns:
        파일 목록을 담은 딕셔너리
    """
    logger = _get_logger(session_id)
    logger.info("문서 목록 조회 시도 | 디렉토리=%s", directory_path)

    try:
        path = Path(directory_path)
        if not path.exists():
            logger.warning("문서 목록 조회 실패 | 디렉토리 없음")
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

        result = {
            "success": True,
            "directory": str(path),
            "files": spec_files,
            "count": len(spec_files),
        }
        logger.info("문서 목록 조회 완료 | 개수=%d", result["count"])
        return result

    except Exception as e:
        logger.exception("문서 목록 조회 실패")
        return {
            "success": False,
            "error": f"Failed to list files in {directory_path}: {str(e)}",
        }
