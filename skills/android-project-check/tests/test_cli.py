import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_project.py"
ARM = "jni/arm64-v8a/libdevice.so"


def elf(alignment=16384, machine=183):
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = struct.pack("<HHIQQQIHHHHHH", 3, machine, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    load = struct.pack("<II6Q", 1, 5, 0, 0, 0, 120, 120, alignment)
    return ident + header + load


class ProjectCheck(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.root = self.folder / "project with spaces"
        self.root.mkdir()

    def aar(self, relative="app/libs/device.aar", entries=None, manifest=True, compression=ZIP_DEFLATED):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(path, "w", compression=compression) as archive:
            if manifest:
                archive.writestr("AndroidManifest.xml", "fixture manifest")
            for name, payload in (entries if entries is not None else {ARM: elf()}).items():
                archive.writestr(name, payload)
        return path

    def command(self, *args, root=None):
        return subprocess.run(
            [sys.executable, "-I", "-B", str(SCRIPT), str(root or self.root), *map(str, args)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def report(self, code=0, status="pass", *args, root=None):
        result = self.command(*args, root=root)
        self.assertEqual(result.returncode, code, result.stderr or result.stdout)
        self.assertTrue(result.stdout.strip(), "Expected scanner JSON: " + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], status)
        return report

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_direct_android_and_uts_paths_only_sorted_and_hashed(self):
        paths = [self.aar("uni_modules/zeta/utssdk/app-android/libs/SDK.AAR"),
                 self.aar("app/libs/a.aar")]
        self.aar("app/libs/nested/ignored.aar", manifest=False)
        self.aar(".gradle/caches/ignored.aar", manifest=False)
        self.aar("other/libs/ignored.aar", manifest=False)
        before = self.snapshot()
        first = self.command()
        second = self.command()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        report = json.loads(first.stdout)
        self.assertEqual([item["source"] for item in report["artifacts"]],
                         ["app/libs/a.aar", "uni_modules/zeta/utssdk/app-android/libs/SDK.AAR"])
        self.assertEqual([item["sha256"] for item in report["artifacts"]],
                         [hashlib.sha256(path.read_bytes()).hexdigest() for path in reversed(paths)])
        native = report["artifacts"][0]["libraries"][0]
        self.assertEqual(native["sha256"], hashlib.sha256(elf()).hexdigest())
        self.assertEqual(native["detected_abi"], "arm64-v8a")
        self.assertEqual(native["elf_alignment"], "pass")
        self.assertNotIn("zip_alignment", first.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_4k_load_alignment_failure_has_segment_values(self):
        self.aar(entries={ARM: elf(4096)})
        report = self.report(1, "fail")
        native = report["artifacts"][0]["libraries"][0]
        self.assertEqual(native["elf_alignment"], "fail")
        self.assertEqual(native["load_issues"],
                         [{"program_header": 0, "p_align": 4096, "p_offset": 0, "p_vaddr": 0}])

    def test_abi_expectations_are_opt_in_and_apply_to_every_aar(self):
        self.aar()
        self.aar("app/libs/resources.aar", entries={})
        baseline = self.report()
        self.assertEqual(baseline["expected_abis"], [])
        report = self.report(1, "fail", "--expect-abi", "arm64-v8a", "--expect-abi", "x86_64")
        self.assertEqual(report["artifacts"][0]["missing_abis"], ["x86_64"])
        self.assertEqual(report["artifacts"][1]["missing_abis"], ["arm64-v8a", "x86_64"])

    def test_abi_mismatch_uses_detected_machine_for_alignment(self):
        self.aar(entries={ARM: elf(machine=62)})
        native = self.report(1, "fail")["artifacts"][0]["libraries"][0]
        self.assertEqual(native["abi_status"], "abi_mismatch")
        self.assertEqual(native["detected_abi"], "x86_64")
        self.assertEqual(native["elf_alignment"], "pass")

    def test_java_and_32_bit_aar_explicitly_have_no_64_bit_alignment_check(self):
        self.aar(entries={})
        header = b"\x7fELF\x01\x01\x01" + bytes(11) + (40).to_bytes(2, "little")
        self.aar("app/libs/arm32.aar", {"jni/armeabi-v7a/libdevice.so": header})
        directory = self.folder / "evidence"
        report = self.report(0, "pass", "--output-dir", directory)
        self.assertEqual([item["elf64_count"] for item in report["artifacts"]], [0, 0])
        self.assertEqual(report["artifacts"][0]["libraries"][0]["elf_alignment"], "not_applicable")
        markdown = (directory / "report.md").read_text(encoding="utf-8")
        self.assertIn("No 64-bit ELF alignment was evaluated", markdown)
        self.assertIn("未检查 64 位 ELF 对齐", markdown)

    def test_no_matches_is_not_pass(self):
        report = self.report(3, "no_matches")
        self.assertEqual(report["artifacts"], [])
        directory = self.folder / "empty evidence"
        self.report(3, "no_matches", "--output-dir", directory)
        self.assertIn("no_matches", (directory / "report.md").read_text(encoding="utf-8"))

    def test_invalid_root_reports_json(self):
        for root in (self.root / "missing", self.aar()):
            with self.subTest(root=root):
                report = self.report(2, "invalid", root=root)
                self.assertTrue(report["errors"])

    def test_missing_manifest_and_invalid_zip_preserve_other_artifact_results(self):
        self.aar("app/libs/a-good.aar")
        self.aar("app/libs/b-fail.aar", {ARM: elf(4096)})
        self.aar("app/libs/c-no-manifest.aar", manifest=False)
        (self.root / "app/libs/d-broken.aar").write_bytes(b"not a zip")
        report = self.report(2, "invalid")
        self.assertEqual([item["status"] for item in report["artifacts"]],
                         ["pass", "fail", "invalid", "invalid"])
        self.assertFalse(report["artifacts"][2]["manifest_present"])
        self.assertTrue(all(item["sha256"] for item in report["artifacts"]))

    def test_malformed_elf_and_unsupported_abi_are_invalid(self):
        for entries in ({ARM: b"not ELF"}, {ARM: elf()[:70]},
                        {"jni/mips/libdevice.so": elf()}, {ARM: elf()[0:5] + b"\x02" + elf()[6:]}):
            with self.subTest(entries=list(entries)):
                self.aar(entries=entries)
                report = self.report(2, "invalid")
                self.assertEqual(report["artifacts"][0]["libraries"][0]["elf_alignment"], "invalid")

    def test_zip_crc_and_unsafe_or_duplicate_members_are_invalid(self):
        for entry in ("../escape", "/absolute", "jni/../lib.so", "jni\\arm64-v8a\\lib.so"):
            with self.subTest(entry=entry):
                self.aar(entries={entry: b"x"})
                self.report(2, "invalid")
        path = self.aar(compression=ZIP_STORED)
        payload = path.read_bytes().replace(elf(), b"X" + elf()[1:], 1)
        path.write_bytes(payload)
        self.report(2, "invalid")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(path, "w") as archive:
                archive.writestr("AndroidManifest.xml", "first")
                archive.writestr("AndroidManifest.xml", "second")
        self.report(2, "invalid")

    def test_malformed_lzma_is_invalid_and_preserves_valid_sibling(self):
        self.aar("app/libs/a-good.aar")
        path = self.aar("app/libs/b-lzma.aar", entries={}, compression=ZIP_STORED)
        with ZipFile(path) as archive:
            entry = archive.getinfo("AndroidManifest.xml")
        payload = bytearray(path.read_bytes())
        payload[8:10] = (14).to_bytes(2, "little")
        central = payload.index(b"PK\x01\x02")
        payload[central + 10:central + 12] = (14).to_bytes(2, "little")
        offset = entry.header_offset + 30 + len(entry.filename)
        # Invalid LZMA stream without requiring an LZMA compressor in the fixture generator.
        payload[offset:offset + entry.file_size] = bytes.fromhex("090405005d00008000ffffffffffffff")
        path.write_bytes(payload)
        report = self.report(2, "invalid")
        self.assertEqual([item["status"] for item in report["artifacts"]], ["pass", "invalid"])
        self.assertIn("Unsupported AAR ZIP compression method", report["artifacts"][1]["errors"][0])

    def test_external_output_is_fresh_bilingual_and_input_read_only(self):
        self.aar(entries={ARM: elf(4096)})
        before = self.snapshot()
        directory = self.folder / "evidence"
        report = self.report(1, "fail", "--output-dir", directory)
        self.assertEqual(json.loads((directory / "report.json").read_bytes()), report)
        markdown = (directory / "report.md").read_text(encoding="utf-8")
        self.assertIn("## English", markdown)
        self.assertIn("## 简体中文", markdown)
        self.assertIn("app/libs/device.aar", markdown)
        self.assertIn("PT_LOAD", markdown)
        self.assertIn("APK ZIP", markdown)
        self.assertNotIn(str(self.root), markdown)
        self.assertEqual(before, self.snapshot())
        outputs = {path.name: path.read_bytes() for path in directory.iterdir()}
        retry = self.command("--output-dir", directory)
        self.assertEqual(retry.returncode, 2)
        self.assertEqual(retry.stdout, "")
        self.assertEqual(outputs, {path.name: path.read_bytes() for path in directory.iterdir()})

    def test_output_inside_project_is_rejected_before_any_write(self):
        self.aar()
        before = self.snapshot()
        result = self.command("--output-dir", self.root / "new evidence")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("output directory", result.stderr)
        self.assertFalse((self.root / "new evidence").exists())
        self.assertEqual(self.snapshot(), before)

    def symlink(self, path, target, directory=False):
        try:
            path.symlink_to(target, target_is_directory=directory)
        except OSError as error:
            self.skipTest("Symlink creation unavailable: " + str(error))

    def test_symlink_candidate_and_directory_are_not_followed(self):
        source = self.aar("elsewhere.aar")
        (self.root / "app/libs").mkdir(parents=True)
        self.symlink(self.root / "app/libs/link.aar", source)
        report = self.report(2, "invalid")
        self.assertTrue(report["errors"])
        self.assertEqual(report["artifacts"], [])
        (self.root / "app/libs/link.aar").unlink()
        (self.root / "app/libs").rmdir()
        self.symlink(self.root / "app/libs", self.folder, directory=True)
        self.report(2, "invalid")

    def test_external_output_symlink_back_into_project_is_rejected(self):
        self.aar()
        self.symlink(self.folder / "project alias", self.root, directory=True)
        result = self.command("--output-dir", self.folder / "project alias/evidence")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("output directory", result.stderr)
        self.assertFalse((self.root / "evidence").exists())

    @unittest.skipUnless(os.name == "nt", "Windows junction behavior")
    def test_windows_junction_is_not_followed(self):
        (self.root / "app").mkdir()
        junction = self.root / "app/libs"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(self.folder)],
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(junction.rmdir)
        self.report(2, "invalid")


if __name__ == "__main__":
    unittest.main()
