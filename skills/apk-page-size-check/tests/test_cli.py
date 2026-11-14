import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_apk.py"
ARM = "lib/arm64-v8a/libdevice.so"
X86 = "lib/x86_64/libdevice.so"
ARM32 = "lib/armeabi-v7a/libdevice.so"


def elf(*, alignment=16384, address=0x10040, machine=183, segment_type=1):
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = struct.pack("<HHIQQQIHHHHHH", 3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    first = struct.pack("<II6Q", 1, 5, 0, 0x8000, 0, 64, 64, 16384)
    second = struct.pack("<II6Q", segment_type, 6, 64, address, 0, 0, 64, alignment)
    return ident + header + first + second


class ApkPageSizeCheck(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.apk = Path(directory.name) / "app.apk"

    def fixture(self, *entries, manifest=True):
        with ZipFile(self.apk, "w") as archive:
            if manifest:
                archive.writestr("AndroidManifest.xml", "fixture manifest")
            for name, payload, compression, boundary in entries:
                info = ZipInfo(name)
                info.compress_type = compression
                if boundary:
                    start = archive.fp.tell() + 30 + len(name.encode("utf-8"))
                    padding = -(start + 4) % boundary
                    info.extra = struct.pack("<HH", 0xCAFE, padding) + bytes(padding)
                archive.writestr(info, payload)

    def report(self, code, status, *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.apk), *map(str, args)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, code, result.stderr or result.stdout)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], status)
        self.assertEqual(report["page_size"], 16384)
        return report

    def check(self, code, status):
        report = self.report(code, status)
        return {item["entry"]: item for item in report["libraries"]}

    def aar(self, filename, entries):
        path = self.apk.with_name(filename)
        with ZipFile(path, "w") as archive:
            archive.writestr("AndroidManifest.xml", "fixture manifest")
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def aar_manifest(self, *artifacts):
        path = self.apk.with_name("resolved aars.json")
        path.write_text(json.dumps({
            "consumer_configuration": ":app:demoDebugRuntimeClasspath",
            "artifacts": [{"coordinate": coordinate, "path": str(aar)} for coordinate, aar in artifacts],
        }), encoding="utf-8")
        return path

    def test_stored_and_compressed_libraries_pass_with_explicit_32_bit_scope(self):
        self.fixture(
            (ARM, elf(), ZIP_STORED, 16384),
            (X86, elf(alignment=65536, machine=62), ZIP_DEFLATED, None),
            (ARM32, b"32-bit fixture", ZIP_STORED, 16384),
        )
        checks = self.check(0, "pass")
        self.assertEqual(checks[ARM]["elf"], "pass")
        self.assertEqual(checks[ARM]["zip"], "pass")
        self.assertEqual(checks[ARM]["zip_data_offset"], 16384)
        self.assertEqual(checks[X86]["elf"], "pass")
        self.assertEqual(checks[X86]["zip"], "compressed")
        self.assertEqual(checks[ARM32]["elf"], "not_applicable")
        self.assertEqual(checks[ARM32]["zip"], "pass")

    def test_independent_alignment_failures_report_library_and_load_segment(self):
        self.fixture(
            (ARM, elf(alignment=4096), ZIP_STORED, 16384),
            (X86, elf(machine=62), ZIP_STORED, 4096),
        )
        checks = self.check(1, "fail")
        self.assertEqual(checks[ARM]["elf"], "fail")
        self.assertEqual(checks[ARM]["zip"], "pass")
        self.assertEqual(checks[ARM]["load_issues"][0]["program_header"], 1)
        self.assertEqual(checks[ARM]["load_issues"][0]["p_align"], 4096)
        self.assertEqual(checks[X86]["elf"], "pass")
        self.assertEqual(checks[X86]["zip"], "fail")
        self.assertEqual(checks[X86]["zip_data_offset"] % 4096, 0)
        self.assertNotEqual(checks[X86]["zip_data_offset"] % 16384, 0)
        self.assertNotIn("origin", checks[ARM])

    def test_failed_libraries_match_resolved_aars_by_path_abi_and_payload(self):
        payload = elf(alignment=4096)
        zip_failure = elf()
        shared = "lib/arm64-v8a/libshared.so"
        changed = "lib/arm64-v8a/libchanged.so"
        passing = "lib/arm64-v8a/libpassing.so"
        self.fixture(
            (ARM, payload, ZIP_DEFLATED, None),
            (shared, zip_failure, ZIP_STORED, None),
            (changed, payload + b"changed after packaging", ZIP_DEFLATED, None),
            (passing, zip_failure, ZIP_DEFLATED, None),
        )
        first = self.aar("first.aar", {
            "jni/arm64-v8a/libdevice.so": payload,
            "jni/arm64-v8a/libshared.so": zip_failure,
            "jni/arm64-v8a/libchanged.so": payload,
            "jni/arm64-v8a/libpassing.so": zip_failure,
        })
        second = self.aar("second.aar", {
            "jni/arm64-v8a/libdevice.so": payload + b"same name, different bytes",
            "jni/arm64-v8a/libshared.so": zip_failure,
            "jni/x86_64/libchanged.so": payload + b"changed after packaging",
            "assets/arm64-v8a/libchanged.so": payload + b"changed after packaging",
        })
        manifest = self.aar_manifest(
            ("example:first:1.0", first.name), ("example:second:1.0", second),
            ("example:first:1.0", first),
        )
        report = self.report(1, "fail", "--aar-manifest", manifest)
        self.assertEqual(report["aar_manifest"]["consumer_configuration"], ":app:demoDebugRuntimeClasspath")
        libraries = {item["entry"]: item for item in report["libraries"]}
        self.assertEqual(libraries[ARM]["origin"], {
            "status": "single_candidate", "sha256": hashlib.sha256(payload).hexdigest(),
            "candidates": [{"coordinate": "example:first:1.0", "aar": str(first.resolve()),
                            "entry": "jni/arm64-v8a/libdevice.so"}],
        })
        self.assertEqual(libraries[shared]["elf"], "pass")
        self.assertEqual(libraries[shared]["zip"], "fail")
        self.assertEqual(libraries[shared]["origin"]["status"], "multiple_candidates")
        self.assertEqual([item["coordinate"] for item in libraries[shared]["origin"]["candidates"]],
                         ["example:first:1.0", "example:second:1.0"])
        self.assertEqual(libraries[changed]["origin"]["status"], "unknown")
        self.assertEqual(libraries[changed]["origin"]["candidates"], [])
        self.assertNotIn("origin", libraries[passing])

    def test_invalid_manifest_or_aar_does_not_report_incomplete_origin_candidates(self):
        self.fixture((ARM, elf(alignment=4096), ZIP_DEFLATED, None))
        first = self.aar("first.aar", {"jni/arm64-v8a/libdevice.so": elf(alignment=4096)})
        broken = self.apk.with_name("broken.aar")
        broken.write_bytes(b"not a zip")
        manifest = self.aar_manifest(("example:first:1.0", first), ("example:broken:1.0", broken))
        report = self.report(2, "invalid", "--aar-manifest", manifest)
        self.assertIn("broken.aar", report["error"])
        self.assertNotIn("origin", report["libraries"][0])
        manifest.write_text('{"artifacts": []}', encoding="utf-8")
        report = self.report(2, "invalid", "--aar-manifest", manifest)
        self.assertIn("consumer_configuration", report["error"])

    def test_compression_does_not_skip_elf_and_offset_must_match_virtual_address(self):
        self.fixture((ARM, elf(address=0x10041), ZIP_DEFLATED, None))
        checks = self.check(1, "fail")
        self.assertEqual(checks[ARM]["elf"], "fail")
        self.assertEqual(checks[ARM]["zip"], "compressed")

    def test_invalid_or_unsupported_elf_is_not_a_pass(self):
        non_loadable = bytearray(elf(segment_type=4))
        struct.pack_into("<I", non_loadable, 64, 4)
        for payload in (b"not ELF", elf()[:140], elf(machine=62), non_loadable):
            with self.subTest(payload=bytes(payload)[:24]):
                self.fixture((ARM, payload, ZIP_DEFLATED, None))
                checks = self.check(2, "invalid")
                self.assertEqual(checks[ARM]["elf"], "invalid")

    def test_no_64_bit_libraries(self):
        self.fixture()
        self.assertEqual(self.check(3, "not_applicable"), {})
        self.fixture((ARM32, b"32-bit fixture", ZIP_STORED, 16384))
        self.assertEqual(self.check(3, "not_applicable")[ARM32]["elf"], "not_applicable")

    def test_invalid_apk_missing_manifest_or_unreadable_zip(self):
        self.fixture(manifest=False)
        self.check(2, "invalid")
        self.apk.write_bytes(b"not a zip")
        self.check(2, "invalid")

    def test_corrupt_library_payload_is_rejected(self):
        self.fixture((ARM, elf(), ZIP_STORED, 16384))
        data = bytearray(self.apk.read_bytes())
        data[16384] = 0
        self.apk.write_bytes(data)
        checks = self.check(2, "invalid")
        self.assertIn("CRC", checks[ARM]["error"])

    def test_inconsistent_zip_local_header_is_rejected(self):
        self.fixture((ARM, elf(), ZIP_STORED, 16384))
        with ZipFile(self.apk) as archive:
            local_header = archive.getinfo(ARM).header_offset
        data = bytearray(self.apk.read_bytes())
        struct.pack_into("<I", data, local_header + 18, 0)  # Compressed size
        self.apk.write_bytes(data)
        checks = self.check(2, "invalid")
        self.assertEqual(checks[ARM]["zip"], "invalid")

    def test_stored_alignment_uses_local_extra_not_central_directory(self):
        self.fixture((ARM, elf(), ZIP_STORED, 16384))
        data = bytearray(self.apk.read_bytes())
        with ZipFile(self.apk) as archive:
            start = archive.start_dir
            manifest_length = len("AndroidManifest.xml")
            central = start + 46 + manifest_length
        extra_length = struct.unpack_from("<H", data, central + 30)[0]
        extra_start = central + 46 + len(ARM)
        del data[extra_start:extra_start + extra_length]
        struct.pack_into("<H", data, central + 30, 0)
        struct.pack_into("<I", data, len(data) - 10, len(data) - 22 - start)
        self.apk.write_bytes(data)
        self.assertEqual(self.check(0, "pass")[ARM]["zip_data_offset"], 16384)

    def test_unsupported_abi_and_duplicate_library_are_invalid(self):
        unknown = "lib/unknown/libdevice.so"
        self.fixture((unknown, elf(), ZIP_STORED, 16384))
        self.check(2, "invalid")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            entry = (ARM, elf(), ZIP_STORED, 16384)
            self.fixture(entry, entry)
        self.check(2, "invalid")


if __name__ == "__main__":
    unittest.main()
