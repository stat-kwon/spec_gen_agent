"""명세 생성 워크플로우에서 출력 파일을 관리하는 저장소 모듈."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from spec_agent.workflows.context import WorkflowContext


class SpecStorage:
    """워크플로우 실행 중 생성되는 산출물을 관리합니다."""

    def __init__(self, context: WorkflowContext) -> None:
        self.context = context
        self._saved_files: List[str] = []

    @property
    def output_dir(self) -> Optional[str]:
        """현재 설정된 출력 디렉토리를 반환합니다."""

        return self.context.project.get("output_dir")

    def prepare_output_directory(self, path: str) -> str:
        """출력 디렉토리를 생성하고 절대 경로를 반환합니다."""

        output_path = Path(path).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        self.context.project["output_dir"] = str(output_path)
        return str(output_path)

    def write_document(
        self,
        agent_name: str,
        content: str,
    ) -> Dict[str, object]:
        """지정된 에이전트 문서를 저장하고 메타데이터를 반환합니다."""

        output_dir = self.output_dir
        if not output_dir:
            raise ValueError("출력 디렉토리가 아직 준비되지 않았습니다.")

        filename = "openapi.json" if agent_name == "openapi" else f"{agent_name}.md"
        file_path = Path(output_dir) / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        is_update = file_path.exists()
        action = "업데이트" if is_update else "생성"

        file_path.write_text(content, encoding="utf-8")
        size = file_path.stat().st_size

        file_path_str = str(file_path)
        if file_path_str not in self._saved_files:
            self._saved_files.append(file_path_str)

        return {
            "filename": filename,
            "file_path": file_path_str,
            "size": size,
            "action": action,
        }

    def saved_files(self) -> List[str]:
        """현재까지 저장된 파일 경로 목록을 반환합니다."""

        return list(self._saved_files)
