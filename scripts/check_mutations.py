"""Проверить обнаружение трёх контрольных мутаций логики продажи."""

import json
import os
import shutil

# Запускается только локальный pytest без оболочки; обоснование: docs/sast.md.
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

from defusedxml import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    (
        "Цена равна начальной ошибочно запрещена",
        "payload.final_price < lot.starting_price",
        "payload.final_price <= lot.starting_price",
    ),
    ("Округление комиссии вниз", "ROUND_HALF_UP", "ROUND_DOWN"),
    (
        "Инвертирован запрет повторной продажи",
        "lot.status != LotStatus.AVAILABLE",
        "lot.status == LotStatus.AVAILABLE",
    ),
]


def run_tests(workspace: Path) -> tuple[int, list[str]]:
    env = os.environ | {
        "PYTHONPATH": os.pathsep.join([str(workspace / "src"), str(workspace)]),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    report = workspace / "results.xml"
    # Команда фиксирована, используются sys.executable и аргументы списка, shell=False.
    result = subprocess.run(  # nosec B603
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_sales_unit.py",
            f"--junitxml={report}",
        ],
        shell=False,
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if not report.exists():
        raise RuntimeError(result.stdout + result.stderr)
    tree = ET.parse(report)
    if any(int(suite.get("errors", "0")) for suite in tree.iter("testsuite")):
        raise RuntimeError("Ошибка запуска контрольных тестов:\n" + result.stdout + result.stderr)
    if any(int(suite.get("skipped", "0")) for suite in tree.iter("testsuite")):
        raise RuntimeError("Контрольные тесты не должны пропускаться.")
    failures = [
        case.get("name", "") for case in tree.iter("testcase") if case.find("failure") is not None
    ]
    return result.returncode, failures


def main() -> None:
    results = []
    with tempfile.TemporaryDirectory(prefix="auctions-mutations-") as directory:
        workspace = Path(directory)
        for name in ["src", "tests"]:
            shutil.copytree(
                ROOT / name, workspace / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        shutil.copy2(ROOT / "pyproject.toml", workspace / "pyproject.toml")
        code_path = workspace / "src" / "auctions" / "services" / "sales.py"
        original = code_path.read_text(encoding="utf-8")
        exit_code, failures = run_tests(workspace)
        if exit_code != 0 or failures:
            raise SystemExit("Исходная логика не проходит контрольные тесты.")
        for name, before, after in MUTATIONS:
            if before not in original:
                raise SystemExit(f"Не найдено условие для мутации: {name}")
            code_path.write_text(original.replace(before, after), encoding="utf-8")
            exit_code, failures = run_tests(workspace)
            detected = exit_code == 1 and bool(failures)
            results.append({"mutation": name, "detected": detected, "failed_tests": failures})
            print(f"{name}: {'обнаружена' if detected else 'НЕ ОБНАРУЖЕНА'}", flush=True)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "mutations.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not all(result["detected"] for result in results):
        raise SystemExit("Тесты не обнаружили все контрольные мутации.")
    print("Обнаружены все 3 контрольные мутации. Отчёт: reports/mutations.json")


if __name__ == "__main__":
    main()
