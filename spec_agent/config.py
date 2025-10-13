"""spec_agent의 설정 관리."""   

import os
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


class Config(BaseModel):
    """spec_agent 시스템의 설정."""   

    # OpenAI 설정
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4")
    openai_temperature: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

    # Strands 설정
    strands_model_provider: str = os.getenv("STRANDS_MODEL_PROVIDER", "openai")
    strands_max_retries: int = int(os.getenv("STRANDS_MAX_RETRIES", "3"))
    strands_timeout: int = int(os.getenv("STRANDS_TIMEOUT", "120"))

    # 출력 설정
    default_output_dir: str = os.getenv("DEFAULT_OUTPUT_DIR", "specs")
    log_level: str = os.getenv("SPEC_AGENT_LOG_LEVEL", "INFO")

    # Git 설정
    git_branch_prefix: str = os.getenv("GIT_BRANCH_PREFIX", "specgen/scenario-3")
    git_commit_prefix: str = os.getenv("GIT_COMMIT_PREFIX", "spec")

    # Agentic Loop 최적화 설정
    incremental_save: bool = os.getenv("INCREMENTAL_SAVE", "true").lower() == "true"
    min_improvement_threshold: float = float(
        os.getenv("MIN_IMPROVEMENT_THRESHOLD", "5.0")
    )
    parallel_processing: bool = (
        os.getenv("PARALLEL_PROCESSING", "true").lower() == "true"
    )
    early_stopping: bool = os.getenv("EARLY_STOPPING", "true").lower() == "true"
    show_progress: bool = os.getenv("SHOW_PROGRESS", "true").lower() == "true"

    # 토큰 최적화 설정
    enable_token_optimization: bool = (
        os.getenv("ENABLE_TOKEN_OPTIMIZATION", "true").lower() == "true"
    )
    max_openapi_size: int = int(
        os.getenv("MAX_OPENAPI_SIZE", "15000")
    )  # 최대 JSON 크기 (문자 수)
    use_minimal_templates: bool = (
        os.getenv("USE_MINIMAL_TEMPLATES", "true").lower() == "true"
    )

    # 품질 및 반복 설정
    quality_threshold: float = float(os.getenv("QUALITY_THRESHOLD", "70.0"))
    consistency_threshold: float = float(os.getenv("CONSISTENCY_THRESHOLD", "75.0"))
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "3"))

    @classmethod
    def from_env(cls) -> "Config":
        """환경 변수로부터 설정 생성."""
        return cls()

    def validate(self) -> bool:
        """필수 설정 검증."""
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")
        return True
