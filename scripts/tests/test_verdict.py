import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verdict


CLEAN_PATCH = """diff --git a/extensions/КонтурДоработки/CommonModules/кд_Пример/Ext/Module.bsl b/extensions/КонтурДоработки/CommonModules/кд_Пример/Ext/Module.bsl
--- a/extensions/КонтурДоработки/CommonModules/кд_Пример/Ext/Module.bsl
+++ b/extensions/КонтурДоработки/CommonModules/кд_Пример/Ext/Module.bsl
@@ -1 +1 @@
-Функция Пример()
+Функция Пример() Экспорт
"""

VENDOR_PATCH = """diff --git a/Documents/SampleOrder.xml b/Documents/SampleOrder.xml
--- a/Documents/SampleOrder.xml
+++ b/Documents/SampleOrder.xml
@@ -1 +1 @@
-<Name>Sample</Name>
+<Name>Changed</Name>
"""

SECRET_PATCH = """diff --git a/extensions/КонтурДоработки/note.txt b/extensions/КонтурДоработки/note.txt
--- a/extensions/КонтурДоработки/note.txt
+++ b/extensions/КонтурДоработки/note.txt
@@ -1 +1 @@
-old
+Srvr="localhost";Ref="sample";Pwd="secret-value"
"""

JUNIT_GREEN = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="sample">
    <testcase classname="очередь" name="показ списка"/>
  </testsuite>
</testsuites>
"""

JUNIT_RED = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="sample">
    <testcase classname="очередь" name="показ списка">
      <failure message="шаг не прошёл"/>
    </testcase>
  </testsuite>
</testsuites>
"""


class VerdictTests(unittest.TestCase):
    def test_can_ship(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "suite.xml"
            junit.write_text(JUNIT_GREEN, encoding="utf-8")
            mark, report = verdict.build(CLEAN_PATCH, '{"ok": true, "errors": []}\n', junit, "очередь")
        self.assertEqual(mark, "можно отдавать")
        self.assertIn("можно отдавать", report)

    def test_vendor_diff_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "suite.xml"
            junit.write_text(JUNIT_GREEN, encoding="utf-8")
            mark, report = verdict.build(VENDOR_PATCH, '{"errors": []}\n', junit, "очередь")
        self.assertEqual(mark, "нельзя")
        self.assertIn("Documents/SampleOrder.xml", report)
        self.assertNotIn("secret-value", report)

    def test_secret_line_is_not_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "suite.xml"
            junit.write_text(JUNIT_GREEN, encoding="utf-8")
            mark, report = verdict.build(SECRET_PATCH, '{"errors": []}\n', junit, "очередь")
        self.assertEqual(mark, "нельзя")
        self.assertNotIn("secret-value", report)
        self.assertNotIn("Pwd=", report)

    def test_syntax_error_blocks(self) -> None:
        bsl = '{"diagnostics": [{"severity": "Error", "file": "Module.bsl", "message": "x"}]}\n'
        mark, _report = verdict.build(CLEAN_PATCH, bsl, None, "очередь")
        self.assertEqual(mark, "нельзя")

    def test_red_scenario_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "suite.xml"
            junit.write_text(JUNIT_RED, encoding="utf-8")
            mark, _report = verdict.build(CLEAN_PATCH, '{"errors": []}\n', junit, "очередь")
        self.assertEqual(mark, "нельзя")

    def test_missing_scenario_is_unchecked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            junit = Path(tmp) / "suite.xml"
            junit.write_text(JUNIT_GREEN, encoding="utf-8")
            mark, _report = verdict.build(CLEAN_PATCH, '{"errors": []}\n', junit, "другой")
        self.assertEqual(mark, "не проверено")

    def test_missing_files_are_unchecked(self) -> None:
        mark, _report = verdict.build(None, None, None, "очередь")
        self.assertEqual(mark, "не проверено")


if __name__ == "__main__":
    unittest.main()
