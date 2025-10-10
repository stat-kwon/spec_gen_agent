"""
Entry point for the spec_agent package.
"""

import sys
from .cli import cli

if __name__ == "__main__":
    sys.exit(cli())
