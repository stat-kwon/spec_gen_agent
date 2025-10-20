"""프롬프트 템플릿 로더 및 렌더러."""

from __future__ import annotations
import yaml
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, ValidationError, model_validator

__all__ = [
    "PromptMetadata",
    "PromptRegistry",
    "PromptTemplate",
    "get_prompt_registry",
    "render_prompt",
]


PROMPTS_ROOT = Path(__file__).resolve().parent
FRONT_MATTER_DELIMITER = "---"
PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


class PromptMetadata(BaseModel):
    """프론트 매터 메타데이터."""

    id: str
    workflow: str
    iteration_mode: str = Field(pattern=r"^(accumulate|replace|append)$")
    feedback_inputs: List[str] = Field(default_factory=list)
    feedback_outputs: List[str] = Field(default_factory=list)
    variables: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_iteration_mode(self) -> "PromptMetadata":
        if self.iteration_mode not in {"accumulate", "replace", "append"}:
            raise ValueError("iteration_mode must be one of accumulate|replace|append")
        return self


@dataclass(frozen=True)
class PromptTemplate:
    """프롬프트 템플릿과 메타데이터."""

    metadata: PromptMetadata
    body: str

    def placeholders(self) -> Set[str]:
        """템플릿 내 플레이스홀더 집합을 반환."""
        return set(PLACEHOLDER_PATTERN.findall(self.body))

    def render(self, context: Dict[str, Any]) -> str:
        """컨텍스트를 주입해 템플릿을 렌더링."""
        required = set(self.metadata.variables) or self.placeholders()
        missing = [key for key in required if key not in context]
        if missing:
            raise ValueError(f"Missing context variables: {', '.join(sorted(missing))}")

        allowed = required.union({"feedback_section"})
        extra = [key for key in context if key not in allowed]
        if extra:
            raise ValueError(
                f"Unexpected context variables: {', '.join(sorted(extra))}"
            )

        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if name not in context:
                raise ValueError(f"Missing value for placeholder '{name}'")
            value = context[name]
            return str(value)

        return PLACEHOLDER_PATTERN.sub(_replace, self.body).strip()


class PromptRegistry:
    """프롬프트 템플릿을 로드/캐시하는 레지스트리."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or PROMPTS_ROOT

    def load(self, relative_path: str) -> PromptTemplate:
        """상대 경로 기준 템플릿을 로드."""
        path = self._root / relative_path
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")

        metadata, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        try:
            prompt_meta = PromptMetadata(**metadata)
        except ValidationError as exc:
            raise ValueError(f"Invalid prompt metadata in {path}") from exc

        return PromptTemplate(metadata=prompt_meta, body=body)


@lru_cache(maxsize=None)
def get_prompt_registry(root: Optional[Path] = None) -> PromptRegistry:
    """레지스트리 싱글턴."""
    return PromptRegistry(root=root)


def render_prompt(relative_path: str, context: Dict[str, Any]) -> str:
    """프롬프트 템플릿을 로드하고 렌더링."""
    registry = get_prompt_registry()
    template = registry.load(relative_path)
    return template.render(context)


def _parse_front_matter(content: str) -> tuple[Dict[str, Any], str]:
    """Markdown front matter(YAML)를 파싱."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != FRONT_MATTER_DELIMITER:
        raise ValueError("Missing front matter delimiter at start of file.")

    try:
        closing_index = lines.index(FRONT_MATTER_DELIMITER, 1)
    except ValueError as exc:
        raise ValueError("Front matter closing delimiter not found.") from exc

    front_matter = "\n".join(lines[1:closing_index])
    body_lines = lines[closing_index + 1 :]
    body = "\n".join(body_lines).lstrip("\n")

    metadata = yaml.safe_load(front_matter) or {}
    if not isinstance(metadata, dict):
        raise ValueError("Front matter must define a mapping.")

    return metadata, body
