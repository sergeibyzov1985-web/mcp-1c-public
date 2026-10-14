"""Read a patch, a syntax report and Vanessa jUnit. Write report.md.

Does not start 1C. Verdict is one of:
  можно отдавать — vendor config untouched, syntax clean, named scenario green
  нельзя         — one of those checks failed
  не проверено   — a required file is missing or the scenario was not found
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ALLOWED_PREFIXES = (
    "extensions/КонтурДоработки/",
    "extensions/КонтурТесты/",
    "extensions/README.md",
    "features/",
    "scripts/",
    "docs/",
    "mcp-1c-dev/",
    ".cursor/rules/",
    "README.md",
    "apache/",
    ".gitignore",
)

VENDOR_MARKERS = (
    "Catalogs/",
    "Documents/",
    "InformationRegisters/",
    "AccumulationRegisters/",
    "CommonModules/",
    "DataProcessors/",
    "Reports/",
    "ChartsOfCharacteristicTypes/",
    "Enums/",
    "Constants/",
    "Subsystems/",
)

SECRET_NAME = re.compile(r"(?i)(^|[\\/])(\.env|htpasswd|credentials|\.cfe|\.dt)([\\/]|$)")
SECRET_LINE = re.compile(
    r"(?i)(pwd|password|passwd|connectionstring)\s*[=:]|"
    r"Srvr\s*=|Ref\s*=.*Pwd"
)
DIFF_PATH = re.compile(r"^diff --git a/(.+?) b/(.+)$")
PLUS_PATH = re.compile(r"^\+\+\+ b/(.+)$")


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def patch_paths(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = DIFF_PATH.match(line) or PLUS_PATH.match(line)
        if not match:
            continue
        path = _norm(match.group(match.lastindex))
        if not path or path == "/dev/null" or path in seen:
            continue
        seen.add(path)
        found.append(path)
    return found


def patch_leaks_secret(text: str) -> bool:
    for line in text.splitlines():
        if line.startswith(("+", "-", " ")) and SECRET_LINE.search(line):
            return True
        if line.startswith(("diff --git", "+++", "---")) and SECRET_NAME.search(line):
            return True
    return False


def _allowed(path: str) -> bool:
    if SECRET_NAME.search(path):
        return False
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def _vendor(path: str) -> bool:
    if path.startswith("extensions/"):
        return False
    return any(marker in path for marker in VENDOR_MARKERS)


def judge_patch(text: str | None) -> tuple[str, list[str]]:
    if text is None:
        return "missing", ["файл изменений не передан"]
    if not text.strip():
        return "missing", ["файл изменений пуст"]
    notes: list[str] = []
    if patch_leaks_secret(text):
        notes.append("в изменениях есть секрет или строка подключения")
    outside: list[str] = []
    vendor: list[str] = []
    for path in patch_paths(text):
        if _vendor(path):
            vendor.append(path)
        elif not _allowed(path):
            outside.append(path)
    if vendor:
        notes.append("типовая конфигурация: " + ", ".join(vendor[:8]))
    if outside:
        notes.append("вне своего кода: " + ", ".join(outside[:8]))
    if notes:
        return "bad", notes
    if not patch_paths(text):
        return "missing", ["в изменениях не видно путей файлов"]
    return "ok", ["типовая конфигурация не задета"]


def judge_bsl(text: str | None) -> tuple[str, list[str]]:
    if text is None:
        return "missing", ["отчёт синтаксиса не передан"]
    if not text.strip():
        return "missing", ["отчёт синтаксиса пуст"]
    errors: list[str] = []
    saw_object = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                return "missing", ["отчёт синтаксиса не разобран"]
        if not isinstance(item, dict):
            continue
        saw_object = True
        errors.extend(_bsl_errors(item))
        if "\n" not in text.strip():
            break
    if not saw_object:
        return "missing", ["отчёт синтаксиса не разобран"]
    if errors:
        return "bad", errors[:8]
    return "ok", ["синтаксис чистый"]


def _bsl_errors(item: dict) -> list[str]:
    found: list[str] = []
    if item.get("ok") is False and not item.get("errors") and not item.get("diagnostics"):
        found.append("синтаксис: проверка не прошла")
    sources: list = []
    for key in ("errors", "diagnostics"):
        value = item.get(key) or []
        if isinstance(value, list):
            sources.extend(value)
    for source in sources:
        if not isinstance(source, dict):
            found.append("синтаксис: ошибка")
            continue
        severity = str(source.get("severity") or source.get("level") or "error").lower()
        if severity not in ("error", "critical", "fatal"):
            continue
        place = str(source.get("file") or source.get("path") or "модуль")
        found.append(f"синтаксис: {place}")
    return found


def _cases(root: ET.Element) -> list[ET.Element]:
    return list(root.iter("testcase"))


def judge_scenario(junit: Path | None, scenario: str) -> tuple[str, list[str]]:
    if junit is None:
        return "missing", ["отчёт сценариев не передан"]
    files = sorted(junit.glob("*.xml")) if junit.is_dir() else ([junit] if junit.is_file() else [])
    if not files:
        return "missing", ["отчёт сценариев не найден"]
    needle = scenario.casefold().strip()
    if not needle:
        return "missing", ["имя сценария не задано"]
    seen = False
    failed = False
    for path in files:
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except (ET.ParseError, OSError):
            return "missing", ["отчёт сценариев не разобран"]
        for case in _cases(root):
            name = f"{case.get('classname') or ''} {case.get('name') or ''}".casefold()
            if needle not in name:
                continue
            seen = True
            if case.find("failure") is not None or case.find("error") is not None:
                failed = True
    if not seen:
        return "missing", [f"сценарий «{scenario}» в отчёте не найден"]
    if failed:
        return "bad", [f"сценарий «{scenario}» красный"]
    return "ok", [f"сценарий «{scenario}» зелёный"]


def decide(patch: str, bsl: str, scenario: str) -> str:
    marks = (patch, bsl, scenario)
    if "bad" in marks:
        return "нельзя"
    if "missing" in marks:
        return "не проверено"
    return "можно отдавать"


def render(verdict: str, sections: list[tuple[str, list[str]]]) -> str:
    lines = ["# Вердикт", "", verdict, ""]
    for title, notes in sections:
        lines.append(f"- {title}: {notes[0]}")
        for extra in notes[1:]:
            lines.append(f"  - {extra}")
    lines.append("")
    return "\n".join(lines)


def load_text(path: str | None) -> str | None:
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    return file.read_text(encoding="utf-8")


def build(patch_text: str | None, bsl_text: str | None, junit: Path | None, scenario: str) -> tuple[str, str]:
    patch_mark, patch_notes = judge_patch(patch_text)
    bsl_mark, bsl_notes = judge_bsl(bsl_text)
    scenario_mark, scenario_notes = judge_scenario(junit, scenario)
    verdict = decide(patch_mark, bsl_mark, scenario_mark)
    report = render(
        verdict,
        [
            ("Изменения", patch_notes),
            ("Синтаксис", bsl_notes),
            ("Сценарий", scenario_notes),
        ],
    )
    return verdict, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Вердикт по готовым файлам. 1С не запускает.")
    parser.add_argument("--patch", required=True, help="unified diff, changes.patch")
    parser.add_argument("--bsl", required=True, help="отчёт синтаксиса, bsl.json")
    parser.add_argument("--junit", required=True, help="файл или папка jUnit Vanessa")
    parser.add_argument("--scenario", required=True, help="имя сценария, который должен быть зелёным")
    parser.add_argument("--out", default="report.md", help="куда писать страницу вердикта")
    args = parser.parse_args(argv)
    verdict, report = build(load_text(args.patch), load_text(args.bsl), Path(args.junit), args.scenario)
    Path(args.out).write_text(report, encoding="utf-8")
    print(verdict)
    return {"можно отдавать": 0, "нельзя": 1, "не проверено": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
