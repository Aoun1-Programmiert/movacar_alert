"""Smoke tests for the reproducible Python environment setup."""

import subprocess
import sys
import venv
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"


def test_requirements_lists_the_test_and_runtime_dependencies() -> None:
    requirements = [
        line.strip()
        for line in REQUIREMENTS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert requirements == ["pytest==9.1.1", "shapely==2.1.2"]


def test_source_modules_import_in_fresh_venv(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv"
    venv.EnvBuilder(with_pip=False, clear=True).create(venv_dir)
    venv_python = venv_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    result = subprocess.run(
        [
            str(venv_python),
            "-c",
            (
                "import src.api.api_client, src.config.settings, "
                "src.admin_cli, "
                "src.loop.poll_loop, src.mailer.smtp_mailer, "
                "src.models.offer, src.parser.offer_parser, "
                "src.storage.sqlite_store"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
