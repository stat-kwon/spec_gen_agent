"""FRS 문서 로딩 및 처리 도구들."""

import re
from pathlib import Path
from typing import Dict, Any
from strands import tool
import importlib.util
import sys
import os

# models.py 직접 로드
models_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models.py')
spec = importlib.util.spec_from_file_location("models", models_path)
models_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models_module)
FRSDocument = models_module.FRSDocument


@tool
def load_frs_document(frs_path: str = "specs/FRS-1.md") -> Dict[str, Any]:
    """
    FRS 마크다운 문서를 로드하고 파싱합니다.

    Args:
        frs_path: FRS 마크다운 파일 경로 (기본값: specs/FRS-1.md)

    Returns:
        FRS 문서 데이터를 담은 딕셔너리
    """
    try:
        # 현재 작업 디렉토리를 기준으로 경로 해석
        path = Path(frs_path)
        
        # 상대 경로인 경우 현재 작업 디렉토리 기준으로 절대 경로로 변환
        if not path.is_absolute():
            path = Path.cwd() / path
        
        # 파일 존재 여부 확인 및 디버깅 정보 포함
        if not path.exists():
            # 대안 경로들 시도
            alternative_paths = [
                Path.cwd() / "specs/FRS-1.md",
                Path.cwd() / "spec_agent" / "specs/FRS-1.md",
                Path(frs_path)
            ]
            
            for alt_path in alternative_paths:
                if alt_path.exists():
                    path = alt_path
                    break
            else:
                raise FileNotFoundError(f"FRS file not found at {path}. Tried: {[str(p) for p in alternative_paths]}")

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract title from first heading
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        title = title_match.group(1) if title_match else path.stem

        frs_doc = FRSDocument(
            title=title,
            content=content,
            metadata={
                "file_path": str(path),
                "file_size": len(content),
                "lines": len(content.splitlines()),
            },
        )

        return {
            "success": True,
            "frs": frs_doc.model_dump(),
            "content": content,
            "title": title,
            "debug_info": f"Successfully loaded from: {path}"
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to load FRS document: {str(e)}", "attempted_path": str(path) if 'path' in locals() else frs_path}


@tool
def extract_frs_metadata(frs_content: str) -> Dict[str, Any]:
    """
    FRS 컨텐츠에서 메타데이터를 추출합니다.

    Args:
        frs_content: 원시 FRS 마크다운 컨텐츠

    Returns:
        추출된 메타데이터를 담은 딕셔너리
    """
    try:
        metadata = {}

        # Extract sections
        sections = re.findall(r"^##\s+(.+)$", frs_content, re.MULTILINE)
        metadata["sections"] = sections

        # Extract requirements count
        requirements_match = re.findall(r"REQ-\d+", frs_content)
        metadata["requirements_count"] = len(requirements_match)

        # Extract service mentions
        service_indicators = []
        if re.search(r"\bAPI\b|\bREST\b|\bendpoint\b", frs_content, re.IGNORECASE):
            service_indicators.append("api")
        if re.search(
            r"\bweb\b|\bUI\b|\bfrontend\b|\bpage\b", frs_content, re.IGNORECASE
        ):
            service_indicators.append("web")

        metadata["suggested_service_types"] = service_indicators

        # Extract complexity indicators
        complexity_score = 0
        complexity_score += len(
            re.findall(r"\bintegration\b|\bexternal\b", frs_content, re.IGNORECASE)
        )
        complexity_score += len(
            re.findall(
                r"\bauthentication\b|\bauthorization\b", frs_content, re.IGNORECASE
            )
        )
        complexity_score += len(
            re.findall(r"\bdatabase\b|\bstorage\b", frs_content, re.IGNORECASE)
        )

        metadata["complexity_score"] = complexity_score
        metadata["complexity_level"] = (
            "high"
            if complexity_score > 5
            else "medium" if complexity_score > 2 else "low"
        )

        return {"success": True, "metadata": metadata}

    except Exception as e:
        return {"success": False, "error": f"Failed to extract FRS metadata: {str(e)}"}
