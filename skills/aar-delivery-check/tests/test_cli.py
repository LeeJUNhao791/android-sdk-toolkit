import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


SKILL = Path(__file__).resolve().parents[1]


class AarCheck(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        subprocess.run(
            [sys.executable, str(SKILL / "examples/generate.py"), str(self.root)],
            check=True,
        )

    def check(self, name, contract=None, *, verify_abi=False):
        flags = ["--verify-abi"] if verify_abi else []
        return subprocess.run(
            [sys.executable, str(SKILL / "scripts/check_aar.py"), str(self.root / name),
             "--expect", str(contract or SKILL / "examples/expect.json"), *flags],
            capture_output=True, text=True,
        )

    def test_delivery_examples(self):
        for name, code, missing in (
            ("complete.aar", 0, []),
            ("missing-x86_64.aar", 1, ["jni/x86_64/libdevice.so"]),
            ("missing-r8-rules.aar", 1, ["proguard.txt"]),
        ):
            with self.subTest(name=name):
                result = self.check(name)
                self.assertEqual(result.returncode, code, result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "fail" if missing else "pass")
                self.assertEqual(report["missing_entries"], missing)
                self.assertEqual(len(report["checks"]), 4)

    def test_abi_verification_passes_for_matching_headers(self):
        result = self.check("complete.aar", verify_abi=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            [(item["expected_abi"], item["detected_abi"], item["status"])
             for item in report["abi_checks"]],
            [("arm64-v8a", "arm64-v8a", "pass"), ("x86_64", "x86_64", "pass")],
        )

    def test_wrong_architecture_is_a_contract_failure_in_abi_mode(self):
        default = self.check("wrong-abi.aar")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertNotIn("abi_checks", json.loads(default.stdout))
        result = self.check("wrong-abi.aar", verify_abi=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["missing_entries"], [])
        arm = report["abi_checks"][0]
        self.assertEqual(arm["entry"], "jni/arm64-v8a/libdevice.so")
        self.assertEqual(arm["status"], "abi_mismatch")
        self.assertEqual(arm["expected_abi"], "arm64-v8a")
        self.assertEqual(arm["detected_abi"], "x86_64")

    def test_absent_library_remains_a_missing_entry(self):
        result = self.check("missing-x86_64.aar", verify_abi=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["missing_entries"], ["jni/x86_64/libdevice.so"])
        self.assertEqual([item["status"] for item in report["abi_checks"]], ["pass"])

    def test_unsupported_elf_header_is_reported_separately(self):
        with ZipFile(self.root / "invalid-elf.aar", "w") as archive:
            archive.writestr("AndroidManifest.xml", '<manifest package="example.device"/>')
            archive.writestr("jni/arm64-v8a/libdevice.so", b"not an ELF")
            header = b"\x7fELF\x02\x02\x01" + bytes(9) + b"\x00\x03\x00\x3e"
            archive.writestr("jni/x86_64/libdevice.so", header)
            archive.writestr("proguard.txt", "-keep class example.Foo")
        result = self.check("invalid-elf.aar", verify_abi=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(
            [item["status"] for item in report["abi_checks"]],
            ["invalid_elf_header", "unsupported_elf_endianness"],
        )

    def test_manifest_is_required_for_an_aar(self):
        with ZipFile(self.root / "no-manifest.aar", "w") as archive:
            archive.writestr("proguard.txt", "-keep class example.Foo")
        result = self.check("no-manifest.aar")
        self.assertEqual(result.returncode, 2)
        self.assertIn("AndroidManifest.xml", result.stderr)

    def test_invalid_archive_and_contract(self):
        (self.root / "broken.aar").write_text("not a ZIP", encoding="utf-8")
        self.assertEqual(self.check("broken.aar").returncode, 2)
        contract = self.root / "bad.json"
        contract.write_text('{"required_entres": ["proguard.txt"]}', encoding="utf-8")
        result = self.check("complete.aar", contract)
        self.assertEqual(result.returncode, 2)
        self.assertIn("required_entres", result.stderr)

    def test_pure_aar_needs_only_manifest_with_empty_contract(self):
        with ZipFile(self.root / "resources.aar", "w") as archive:
            archive.writestr("AndroidManifest.xml", '<manifest package="example.resources"/>')
        contract = self.root / "empty.json"
        contract.write_text("{}", encoding="utf-8")
        result = self.check("resources.aar", contract)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["missing_entries"], [])
