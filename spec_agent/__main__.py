"""
spec_agent 패키지의 진입점.
"""

import sys
from .cli import cli

if __name__ == "__main__":
    sys.exit(cli())
