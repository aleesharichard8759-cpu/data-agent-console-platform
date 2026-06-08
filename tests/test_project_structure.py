from pathlib import Path

REQUIRED_PATHS = [
    "app/main.py",
    "app/core/config.py",
    "app/core/errors.py",
    "app/domain/__init__.py",
    "app/policy/__init__.py",
    "app/tools/__init__.py",
    "app/hooks/__init__.py",
    "app/agents/__init__.py",
    "app/runtime/__init__.py",
    "app/security/__init__.py",
    "app/audit/__init__.py",
    "app/memory/__init__.py",
    "app/evals/__init__.py",
    "app/connectors/__init__.py",
    "tests/test_health.py",
    "tests/test_project_structure.py",
    "docs/architecture.md",
    "README.md",
    "pyproject.toml",
]


def test_required_project_structure_exists() -> None:
    root = Path(__file__).resolve().parents[1]

    missing = [path for path in REQUIRED_PATHS if not (root / path).exists()]

    assert missing == []


def test_readme_declares_security_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "Agent 不直接访问生产数据" in readme
    assert "DataTool" in readme
    assert "Policy Engine" in readme
    assert "SQL Gateway" in readme

