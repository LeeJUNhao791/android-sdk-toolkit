import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/jni_doctor.py"


class JniDoctor(unittest.TestCase):
    def diagnose(self, log, machine=None, library=None):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder) / "app.apk"
            trace = Path(folder) / "log.txt"
            trace.write_text(log, encoding="utf-8")
            with ZipFile(apk, "w") as archive:
                archive.writestr("AndroidManifest.xml", "fixture manifest")
                if machine is not None:
                    header = b"\x7fELF\x02\x01\x01" + bytes(9)
                    header += struct.pack("<HH", 3, machine)
                    archive.writestr("lib/arm64-v8a/libdevice.so", header)
            args = ["--library", library] if library else []
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(apk), "--abi", "arm64-v8a",
                 "--log", str(trace), *args],
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_missing_reported_library(self):
        result = self.diagnose(
            'java.lang.UnsatisfiedLinkError: PathClassLoader couldn\'t find "libdevice.so"'
        )
        self.assertEqual(result["kind"], "library_absent_from_apk")
        self.assertEqual(result["entry"], "lib/arm64-v8a/libdevice.so")

    def test_wrong_elf_machine(self):
        result = self.diagnose(
            "java.lang.UnsatisfiedLinkError: dlopen failed: wrong architecture",
            machine=62, library="libdevice.so",
        )
        self.assertEqual(result["kind"], "abi_mismatch")
        self.assertEqual(result["elf_machine"], 62)
        self.assertEqual(result["expected_elf_machine"], 183)

    def test_no_implementation_found(self):
        result = self.diagnose(
            "java.lang.UnsatisfiedLinkError: No implementation found for int example.call()",
            machine=183, library="libdevice.so",
        )
        self.assertEqual(result["kind"], "jni_binding_failure")
        self.assertEqual(result["evidence"], "log")

    def test_existing_entry_does_not_explain_loader_error(self):
        result = self.diagnose(
            'java.lang.UnsatisfiedLinkError: dlopen failed: library "libdevice.so" not found',
            machine=183,
        )
        self.assertEqual(result["kind"], "undetermined")

    def test_log_without_link_error(self):
        result = self.diagnose("roundTrip returned 42", library="libdevice.so")
        self.assertEqual(result["kind"], "undetermined")
