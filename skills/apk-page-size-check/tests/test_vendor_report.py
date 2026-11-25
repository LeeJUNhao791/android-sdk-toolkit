import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/render_vendor_report.py"
APK_ENTRY = "lib/arm64-v8a/libsample.so"
AAR_ENTRY = "jni/arm64-v8a/libsample.so"
COORDINATE = "example.vendor:sdk:1.0"
APK_SO_SHA = "a" * 64
MERGED_SO_SHA = "b" * 64
ARCHIVE_SHA = "c" * 64


def checker_report(elf="fail", zip_result="pass"):
    library = {
        "entry": APK_ENTRY, "abi": "arm64-v8a", "elf": elf, "zip": zip_result,
        "load_issues": [{"program_header": 2, "p_align": 4096, "p_offset": 128,
                         "p_vaddr": 4224}] if elf == "fail" else [],
        "zip_data_offset": 16384 if zip_result == "pass" else 4096,
        "origin": {
            "status": "single_candidate", "sha256": APK_SO_SHA,
            "candidates": [{"coordinate": COORDINATE, "entry": AAR_ENTRY,
                            "aar": "C:/private/vendor.aar", "sha256": ARCHIVE_SHA}],
        },
    }
    return {"apk": "/home/private/app.apk", "page_size": 16384, "libraries": [library],
            "status": "fail" if "fail" in (elf, zip_result) else "pass",
            "aar_manifest": {"path": "C:/private/manifest.json",
                             "consumer_configuration": ":private:runtime"}}


class VendorReport(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.input = Path(directory.name) / "private-input.json"
        self.output = Path(directory.name) / "report.md"

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(self.input), *map(str, args)],
            capture_output=True, encoding="utf-8",
        )

    def render(self, report, *args):
        self.input.write_text(json.dumps(report), encoding="utf-8-sig")
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_elf_failure_with_single_direct_candidate_produces_bilingual_draft(self):
        report = self.render(checker_report())
        for expected in ("## 中文", "## English", "Supplier follow-up", "供应商跟进",
                         "among the supplied AARs", "direct SHA-256",
                         APK_ENTRY, AAR_ENTRY, COORDINATE, APK_SO_SHA,
                         "APK SO SHA-256", "p_align=4096", "p_offset=128", "p_vaddr=4224",
                         "16384", "static"):
            self.assertIn(expected, report)
        for private in ("C:/private", "/home/private", ":private:runtime", ARCHIVE_SHA):
            self.assertNotIn(private, report)

    def test_verified_strip_chain_distinguishes_apk_and_pre_strip_so_hashes(self):
        data = checker_report()
        data["native_provenance"] = {"status": "verified", "variant": "do-not-print",
                                     "path": "C:/private/provenance.json"}
        data["libraries"][0]["origin"].update(
            method="gradle_strip_chain", merged_sha256=MERGED_SO_SHA,
        )
        report = self.render(data)
        self.assertIn("verified same-build Gradle strip chain", report)
        self.assertIn("Verify AAR ELF", report)
        self.assertIn("复查 AAR ELF", report)
        self.assertIn("If that member also fails", report)
        self.assertIn("If it passes, investigate stripping and packaging", report)
        self.assertNotIn("Supplier follow-up", report)
        self.assertIn("APK SO SHA-256", report)
        self.assertIn("Pre-strip SO SHA-256", report)
        self.assertIn(APK_SO_SHA, report)
        self.assertIn(MERGED_SO_SHA, report)
        self.assertIn(COORDINATE, report)
        self.assertNotIn("do-not-print", report)
        self.assertNotIn("C:/private", report)

        data["native_provenance"]["status"] = "apk_mismatch"
        report = self.render(data)
        self.assertIn("More evidence needed", report)
        self.assertNotIn(COORDINATE, report)
        self.assertNotIn(MERGED_SO_SHA, report)

    def test_strip_chain_metadata_cannot_be_reported_as_a_direct_match(self):
        data = checker_report()
        data["native_provenance"] = {"status": "verified"}
        library = data["libraries"][0]
        origin = library["origin"]
        for extra in ({"merged_sha256": MERGED_SO_SHA},
                      {"method": "direct_sha256", "merged_sha256": MERGED_SO_SHA}, {}):
            with self.subTest(extra=extra):
                library["origin"] = {**origin, **extra}
                report = self.render(data)
                self.assertIn("More evidence needed", report)
                self.assertNotIn("direct SHA-256", report)
                self.assertNotIn(COORDINATE, report)

        library["origin"] = {**origin, "method": "direct_sha256"}
        self.assertIn("Supplier follow-up", self.render(data))

    def test_zip_only_points_to_packaging_even_with_candidate(self):
        report = self.render(checker_report(elf="pass", zip_result="fail"))
        self.assertIn("App packaging", report)
        self.assertIn("应用打包", report)
        self.assertNotIn("Supplier follow-up", report)
        self.assertNotIn(COORDINATE, report)
        self.assertIn("4096", report)

    def test_combined_failure_has_both_actions(self):
        report = self.render(checker_report(zip_result="fail"))
        self.assertIn("App packaging", report)
        self.assertIn("Supplier follow-up", report)

    def test_unknown_multiple_and_missing_candidates_require_evidence(self):
        for status in ("unknown", "multiple_candidates", None):
            with self.subTest(status=status):
                data = checker_report()
                library = data["libraries"][0]
                if status is None:
                    del library["origin"]
                else:
                    origin = library["origin"]
                    origin["status"] = status
                    extra = dict(origin["candidates"][0], coordinate="example.other:sdk:1.0")
                    origin["candidates"] = [origin["candidates"][0], extra] if status == "multiple_candidates" else []
                report = self.render(data)
                self.assertIn("More evidence needed", report)
                self.assertIn("补充证据", report)
                self.assertNotIn("Supplier follow-up", report)
                self.assertNotIn(COORDINATE, report)
                self.assertNotIn("example.other", report)

    def test_all_pass_and_no_64_bit_give_distinct_results(self):
        data = checker_report(elf="pass")
        report = self.render(data)
        self.assertIn("Applicable checks passed", report)
        self.assertNotIn("Supplier follow-up", report)
        data.update(status="not_applicable", libraries=[])
        report = self.render(data)
        self.assertIn("No ARM64 or x86-64 libraries", report)
        self.assertNotIn("Applicable checks passed", report)

    def test_untrusted_text_cannot_create_markdown_or_echo_paths(self):
        data = checker_report()
        library = data["libraries"][0]
        origin = library["origin"]
        candidate = origin["candidates"][0]
        for value in ("bad:module:https://private.invalid/key",
                      "C:relative:secret", "group:module:../secret",
                      "group:module:1" + chr(96) + "\n![secret](http://private.invalid)"):
            with self.subTest(coordinate=value):
                candidate["coordinate"] = value
                report = self.render(data)
                self.assertIn("More evidence needed", report)
                for fragment in ("private.invalid", "secret", "relative"):
                    self.assertNotIn(fragment, report)
        fake_token = "ghp_" + "A" * 36
        candidate["coordinate"] = "example.vendor:sdk:" + fake_token
        report = self.render(data)
        self.assertIn("More evidence needed", report)
        self.assertNotIn(fake_token, report)

        candidate["coordinate"] = COORDINATE
        library["entry"] = f"lib/arm64-v8a/lib{fake_token}.so"
        candidate["entry"] = f"jni/arm64-v8a/lib{fake_token}.so"
        report = self.render(data)
        self.assertIn("More evidence needed", report)
        self.assertNotIn(fake_token, report)

        library["entry"] = "lib/arm64-v8a/../../private/key.so"
        candidate["entry"] = "jni/arm64-v8a/../../private/key.so"
        origin["sha256"] = chr(96) + "\n<script>secret</script>"
        data["token"] = "ghp_bogus"
        report = self.render(data)
        self.assertIn("More evidence needed", report)
        for private in ("private", "key.so", "<script>", "ghp_bogus", COORDINATE):
            self.assertNotIn(private, report)

    def test_invalid_input_reports_generic_error_without_writing(self):
        for raw in ('{"/private/token":', json.dumps({
                "status": "invalid", "page_size": 16384, "libraries": [],
                "error": "C:/private/token",
        })):
            with self.subTest(input=raw):
                self.input.write_text(raw, encoding="utf-8")
                result = self.run_cli("--output", self.output)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("valid 16 KB checker JSON", result.stderr)
                self.assertNotIn("private", result.stderr)
                self.assertFalse(self.output.exists())

    def test_accepts_utf16_json_from_windows_powershell_redirection(self):
        self.input.write_text(json.dumps(checker_report()), encoding="utf-16")
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Supplier follow-up", result.stdout)

    def test_output_writes_utf8_and_preserves_existing_files(self):
        expected = self.render(checker_report())
        self.assertEqual(self.run_cli("-o", self.output).returncode, 0)
        self.assertEqual(self.output.read_text(encoding="utf-8"), expected)
        result = self.run_cli("-o", self.input)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("private-input.json", result.stderr)
        self.assertEqual(json.loads(self.input.read_text(encoding="utf-8-sig")), checker_report())
