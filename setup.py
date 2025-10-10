from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="spec-agent",
    version="0.1.0",
    author="Spec Agent Team",
    description="Automated specification document generator using AI agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
    install_requires=[
        "strands-agents[a2a,openai]==0.3.0",
        "strands-agents-tools==0.1.0",
        "pydantic==2.5.0",
        "markdown==3.5.0",
        "click==8.1.7",
        "python-dotenv==1.0.0",
        "jsonschema==4.20.0",
    ],
    entry_points={
        "console_scripts": [
            "spec-agent=spec_agent.cli:cli",
        ],
    },
)
