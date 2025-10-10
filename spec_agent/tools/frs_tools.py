"""FRS document loading and processing tools."""

import re
from pathlib import Path
from typing import Dict, Any
from strands import tool
from ..models import FRSDocument


@tool
def load_frs_document(frs_path: str) -> Dict[str, Any]:
    """
    Load and parse an FRS markdown document.

    Args:
        frs_path: Path to the FRS markdown file

    Returns:
        Dictionary containing FRS document data
    """
    try:
        path = Path(frs_path)
        if not path.exists():
            raise FileNotFoundError(f"FRS file not found: {frs_path}")

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
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to load FRS document: {str(e)}"}


@tool
def extract_frs_metadata(frs_content: str) -> Dict[str, Any]:
    """
    Extract metadata from FRS content.

    Args:
        frs_content: Raw FRS markdown content

    Returns:
        Dictionary containing extracted metadata
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
