"""Historical migrations must remain renderable for a fresh deployment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_clean_upgrade_sql_renders_through_current_head() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root / "contracts" / "python")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=repo_root / "api",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "0008_enrollment_account_identity" in result.stderr


def test_clean_downgrade_sql_renders_back_to_base() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repo_root / "contracts" / "python")
    result = subprocess.run(
        [sys.executable, "-B", "-m", "alembic", "downgrade", "head:base", "--sql"],
        cwd=repo_root / "api",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "0001_initial_skeleton" in result.stderr
