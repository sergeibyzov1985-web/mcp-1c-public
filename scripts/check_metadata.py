"""Check extension XML: prefix, synonym, attributes, subsystem, list-form link.

Does not start 1C. A new kind of object is a folder name in FOLDERS.
Objects that stay out of the subsystem are SKIP_MEMBERSHIP.
Adopted objects without our prefix are SKIP_PREFIX.
Catalogs and documents of the product extension need a Vanessa list link
unless their full name is listed in FORM_EXCEPTIONS.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MD = "http://v8.1c.ru/8.3/MDClasses"
V8 = "http://v8.1c.ru/8.1/data/core"
XR = "http://v8.1c.ru/8.3/xcf/readable"

FOLDERS = {
    "Catalog": "Catalogs",
    "CommonModule": "CommonModules",
    "Document": "Documents",
    "HTTPService": "HTTPServices",
    "Language": "Languages",
    "Role": "Roles",
    "Subsystem": "Subsystems",
}

SKIP_PREFIX = ("Language",)
SKIP_MEMBERSHIP = ("Language", "Role", "Subsystem")
LIST_LINKS = {"Catalog": "Справочник", "Document": "Документ"}
FORM_EXCEPTIONS: tuple[str, ...] = ()

EXTENSIONS = {
    "КонтурДоработки": "кд_",
    "КонтурТесты": "кт_",
}


def _local(tag: str) -> str:
    return tag.split("}")[-1]


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


def problems(root: Path) -> list[str]:
    found: list[str] = []
    features = ""
    feature_root = root / "features"
    if feature_root.is_dir():
        features = "\n".join(path.read_text(encoding="utf-8") for path in feature_root.rglob("*.feature"))
    for folder, prefix in EXTENSIONS.items():
        ext = root / "extensions" / folder
        config = ext / "Configuration.xml"
        if not config.is_file():
            found.append(f"нет {config.name} в {folder}")
            continue
        tree = ET.parse(config)
        children = tree.getroot().find(f"{{{MD}}}Configuration/{{{MD}}}ChildObjects")
        if children is None:
            found.append(f"{folder}: нет списка объектов")
            continue
        content = _subsystem_content(ext)
        for child in list(children):
            kind = _local(child.tag)
            name = _text(child)
            if not name or kind not in FOLDERS:
                continue
            ref = f"{kind}.{name}"
            path = ext / FOLDERS[kind] / f"{name}.xml"
            if kind not in SKIP_PREFIX and not name.startswith(prefix):
                found.append(f"{ref}: имя без префикса {prefix}")
            if not path.is_file():
                found.append(f"{ref}: нет файла")
                continue
            found.extend(_object_problems(path, ref, prefix))
            if kind not in SKIP_MEMBERSHIP and ref not in content:
                found.append(f"{ref}: не входит в подсистему")
            if folder == "КонтурДоработки" and kind in LIST_LINKS and ref not in FORM_EXCEPTIONS:
                link = f"e1cib/list/{LIST_LINKS[kind]}.{name}"
                if link not in features:
                    found.append(f"{ref}: нет открытия списка в сценарии")
    return found


def _subsystem_content(ext: Path) -> set[str]:
    content: set[str] = set()
    folder = ext / "Subsystems"
    if not folder.is_dir():
        return content
    for path in folder.glob("*.xml"):
        tree = ET.parse(path)
        for item in tree.getroot().iter(f"{{{XR}}}Item"):
            content.add(_text(item))
    return content


def _object_problems(path: Path, ref: str, prefix: str) -> list[str]:
    found: list[str] = []
    tree = ET.parse(path)
    root = tree.getroot()
    properties = None
    for element in root.iter(f"{{{MD}}}Properties"):
        properties = element
        break
    if properties is not None:
        synonym = properties.find(f"{{{MD}}}Synonym")
        if synonym is not None:
            for item in synonym.iter(f"{{{V8}}}content"):
                if prefix in _text(item):
                    found.append(f"{ref}: префикс в синониме")
    for element in root.iter(f"{{{MD}}}Attribute"):
        name_node = None
        for child in list(element):
            if _local(child.tag) == "Properties":
                name_node = child.find(f"{{{MD}}}Name")
                break
        if name_node is None:
            name_node = element.find(f"{{{MD}}}Name")
        attr = _text(name_node)
        if attr.startswith(prefix):
            found.append(f"{ref}.{attr}: у реквизита свой префикс")
    return found


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    found = problems(root)
    if not found:
        print("метаданные: ок")
        return 0
    for line in found:
        print(line)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
