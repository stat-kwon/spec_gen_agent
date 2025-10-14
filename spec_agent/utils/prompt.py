from pathlib import Path


def get_system_prompt(name: str) -> str:
    """
    system_prompt/{name}.md 파일을 읽어 반환한다.

    Args:
        name: 프롬프트 파일 이름 (확장자 없이). 예: "requirements", "design"

    Returns:
        파일 내용을 문자열로 반환
    """
    prompts_dir = Path(__file__).resolve().parents[1] / "agents" / "system_prompt"
    prompt_path = prompts_dir / f"{name}.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8").lstrip("\ufeff")
