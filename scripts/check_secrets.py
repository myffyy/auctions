"""Проверить отслеживаемые файлы рабочего дерева, не включая локальные секреты."""

import shutil
import subprocess  # nosec B404
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")  # nosec B603 B607
with tempfile.TemporaryDirectory(prefix="auctions-secrets-") as tmp:
    destination = Path(tmp)
    for item in files:
        if not item:
            continue
        relative = Path(item.decode())
        source = root / relative
        if source.is_file() and not source.is_symlink():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    (root / "reports").mkdir(exist_ok=True)
    result = subprocess.run(  # nosec B603 B607
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{destination}:/src:ro",
            "-v",
            f"{root / 'reports'}:/reports",
            "zricethezav/gitleaks:v8.24.2",
            "detect",
            "--source",
            "/src",
            "--no-git",
            "--redact=100",
            "--report-format",
            "json",
            "--report-path",
            "/reports/secrets.json",
        ],
        check=False,
    )
    raise SystemExit(result.returncode)
