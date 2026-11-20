import hashlib
import json
import os
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from test_cli import ARM, elf


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/github_action.py"
GENERATE = ROOT / "examples/generate_origins.py"


class GithubAction(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="apk action ")
        self.addCleanup(directory.cleanup)
        self.workspace = Path(directory.name)
        self.apk = self.workspace / "app with spaces.apk"
        self.summary = self.workspace / "summary.md"
        self.output = self.workspace / "outputs.txt"
        self.runner = self.workspace / "runner"
        self.runner.mkdir()

    def fixture(self, entries=()):
        with ZipFile(self.apk, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("AndroidManifest.xml", "synthetic fixture manifest")
            for name, payload in entries:
                archive.writestr(name, payload)

    def run_action(self, apk=None, manifest="", expected_exit=0, provenance=""):
        environment = {
            **os.environ,
            "INPUT_APK": str(apk if apk is not None else self.apk.name),
            "INPUT_AAR_MANIFEST": str(manifest),
            "INPUT_NATIVE_PROVENANCE": str(provenance),
            "GITHUB_WORKSPACE": str(self.workspace),
            "RUNNER_TEMP": str(self.runner),
            "GITHUB_STEP_SUMMARY": str(self.summary),
            "GITHUB_OUTPUT": str(self.output),
        }
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT)], cwd=ROOT,
            env=environment, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected_exit, result.stderr or result.stdout)
        outputs = dict(line.split("=", 1) for line in self.output.read_text(encoding="utf-8").splitlines())
        report_path = Path(outputs["report"])
        self.assertTrue(report_path.is_relative_to(self.runner))
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["status"], outputs["status"])
        return outputs, report, self.summary.read_text(encoding="utf-8")

    def test_pass_uses_consumer_workspace_and_writes_report_and_summary(self):
        self.fixture([(ARM, elf())])
        outputs, report, summary = self.run_action()
        self.assertEqual(outputs["status"], "pass")
        self.assertEqual(outputs["exit-code"], "0")
        self.assertTrue(Path(report["apk"]).samefile(self.apk))
        self.assertIn("**pass**", summary)
        self.assertIn(ARM, summary)
        self.assertIn("Static alignment", summary)

    def test_failure_keeps_all_candidate_states_in_summary_and_report(self):
        runpy.run_path(str(GENERATE))["generate"](self.workspace)
        outputs, report, summary = self.run_action(
            "app.apk", "resolved-aars.json", expected_exit=1,
        )
        self.assertEqual(outputs["exit-code"], "1")
        self.assertEqual(outputs["status"], "fail")
        self.assertEqual([item["origin"]["status"] for item in report["libraries"]],
                         ["single_candidate", "multiple_candidates", "unknown"])
        for value in ("single_candidate", "multiple_candidates", "unknown",
                      "example:first:1.0", "example:second:1.0", "libchanged.so"):
            self.assertIn(value, summary)
        self.assertIn("supplied AAR", summary)

    def test_strip_evidence_survives_zip_only_failure_and_is_explained_in_summary(self):
        stripped = elf()
        merged = stripped + b"debug symbols"
        with ZipFile(self.apk, "w") as archive:
            archive.writestr("AndroidManifest.xml", "fixture")
            archive.writestr(ARM, stripped)
        aar = self.workspace / "source.aar"
        with ZipFile(aar, "w") as archive:
            archive.writestr("AndroidManifest.xml", "fixture")
            archive.writestr("jni/" + ARM[4:], merged)
        manifest = self.workspace / "aars.json"
        manifest.write_text(json.dumps({
            "consumer_configuration": ":app:debugRuntimeClasspath",
            "artifacts": [{"coordinate": "example:source:1", "path": aar.name}],
        }), encoding="utf-8")
        provenance = self.workspace / "native provenance.json"
        provenance.write_text(json.dumps({
            "variant": "debug",
            "apk_sha256": hashlib.sha256(self.apk.read_bytes()).hexdigest(),
            "aar_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "libraries": {ARM: {
                "merged_sha256": hashlib.sha256(merged).hexdigest(),
                "stripped_sha256": hashlib.sha256(stripped).hexdigest(),
            }},
        }), encoding="utf-8")
        _, report, summary = self.run_action(manifest=manifest.name, provenance=provenance.name, expected_exit=1)
        library = report["libraries"][0]
        self.assertEqual((library["elf"], library["zip"]), ("pass", "fail"))
        self.assertEqual(library["origin"]["method"], "gradle_strip_chain")
        self.assertIn("example:source:1", summary)
        self.assertIn("gradle_strip_chain", summary)
        self.assertIn("APK packaging", summary)

    def test_failure_without_manifest_requests_aar_list(self):
        self.fixture([(ARM, elf(alignment=4096))])
        outputs, report, summary = self.run_action(expected_exit=1)
        self.assertEqual(outputs["status"], "fail")
        self.assertNotIn("origin", report["libraries"][0])
        self.assertIn("not_requested", summary)
        self.assertIn("aar-manifest", summary)

    def test_invalid_apk_and_manifest_fail_with_report(self):
        self.apk.write_bytes(b"not an APK")
        outputs, _, summary = self.run_action(expected_exit=2)
        self.assertEqual(outputs["status"], "invalid")
        self.assertIn("File is not a zip file", summary)
        self.fixture([(ARM, elf(alignment=4096))])
        manifest = self.workspace / "broken.json"
        manifest.write_text("{}", encoding="utf-8")
        outputs, _, summary = self.run_action(manifest=manifest.name, expected_exit=2)
        self.assertEqual(outputs["exit-code"], "2")
        self.assertIn("consumer_configuration", summary)

    def test_no_64_bit_libraries_is_explicitly_not_applicable(self):
        self.fixture()
        outputs, _, summary = self.run_action()
        self.assertEqual(outputs["exit-code"], "3")
        self.assertEqual(outputs["status"], "not_applicable")
        self.assertIn("No arm64-v8a or x86_64", summary)

    def test_summary_escapes_library_names_and_preserves_other_steps(self):
        self.summary.write_text("Existing step summary\n", encoding="utf-8")
        name = "lib/arm64-v8a/<img src=x>|`[x]\nattack.so"
        self.fixture([(name, elf(alignment=4096))])
        _, report, summary = self.run_action(expected_exit=1)
        self.assertEqual(report["libraries"][0]["entry"], name)
        self.assertTrue(summary.startswith("Existing step summary\n"))
        self.assertNotIn("<img src=x>", summary)
        self.assertIn("&lt;img src=x&gt;", summary)
        self.assertIn("&#124;", summary)
        self.assertNotIn("\nattack.so", summary)

    def test_repeated_calls_keep_distinct_reports(self):
        self.fixture([(ARM, elf())])
        first, _, _ = self.run_action()
        self.fixture([(ARM, elf(alignment=4096))])
        second, _, _ = self.run_action(expected_exit=1)
        self.assertNotEqual(first["report"], second["report"])
        self.assertEqual(json.loads(Path(first["report"]).read_text())["status"], "pass")


if __name__ == "__main__":
    unittest.main()
