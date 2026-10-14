"""Завершить SAST с ошибкой при замечаниях или непроверенных файлах."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    report_path = ROOT / "reports" / "sast.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["errors"]:
        raise SystemExit("SAST не проверил все файлы. Подробности: reports/sast.json")
    if report["results"]:
        raise SystemExit("SAST обнаружил замечания. Подробности: reports/sast.json")
    print("SAST: замечаний и ошибок анализа нет. Отчёт: reports/sast.json")


if __name__ == "__main__":
    main()
