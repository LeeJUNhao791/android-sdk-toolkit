import hashlib
import unittest

import test_cli as fixtures


class SourceHints(unittest.TestCase):
    setUp = fixtures.ProjectCheck.setUp
    aar = fixtures.ProjectCheck.aar
    command = fixtures.ProjectCheck.command
    report = fixtures.ProjectCheck.report
    snapshot = fixtures.ProjectCheck.snapshot
    symlink = fixtures.ProjectCheck.symlink

    def source(self, text, relative="app/src/main/cpp/pages.cpp"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_contextual_definitions_and_page_alignment_are_advisory_and_hashed(self):
        self.aar()
        text = "#define PAGE_SIZE 4096\nconstexpr auto page_size = 0x1000;\nauto page_base = address & ~4095;\nauto aligned_page = (address / 4096) * 4096;\n"
        source = self.source(text)
        before = self.snapshot()
        report = self.report(0, "pass", "--source-file", source.relative_to(self.root).as_posix())
        advisory = report["source_advisories"]
        self.assertEqual(advisory["status"], "hints")
        self.assertEqual(advisory["files"], [{"source": "app/src/main/cpp/pages.cpp",
                          "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}])
        self.assertEqual([hint["line"] for hint in advisory["hints"]], [1, 2, 3, 4])
        self.assertEqual([hint["rule"] for hint in advisory["hints"]],
                         ["page_size_definition", "page_size_definition", "page_alignment_literal", "page_alignment_literal"])
        self.assertEqual(self.snapshot(), before)

    def test_unrelated_4096_comments_strings_and_dynamic_page_size_have_no_hints(self):
        self.aar()
        self.source('char buffer[4096];\nint count = 4096;\nauto page_count = 4096;\n'
                    '// #define PAGE_SIZE 4096\n/*\n#define PAGE_SIZE 4096\n*/\n'
                    'const char* s = "PAGE_SIZE = 4096";\n'
                    'auto page_size = sysconf(_SC_PAGESIZE);\n'
                    'auto page_base = address & ~(page_size - 1);\n'
                    'auto buffer = bytes / 4096;\n#define PAGE_SIZE 40960\n')
        report = self.report(0, "pass", "--source-file", "app/src/main/cpp/pages.cpp")
        self.assertEqual(report["source_advisories"]["status"], "no_hints")
        self.assertEqual(report["source_advisories"]["hints"], [])
        self.assertNotIn("source_advisories", self.report())

    def test_hints_preserve_no_matches_and_fail_and_invalid_precedence(self):
        self.source("#define PAGE_SIZE 4096\n")
        args = ("--source-file", "app/src/main/cpp/pages.cpp")
        self.assertEqual(self.report(3, "no_matches", *args)["source_advisories"]["status"], "hints")
        self.aar(entries={fixtures.ARM: fixtures.elf(4096)})
        self.report(1, "fail", *args)
        report = self.report(2, "invalid", *args, "--source-file", "missing.cpp")
        self.assertEqual(report["artifacts"][0]["status"], "fail")
        self.assertEqual(report["source_advisories"]["status"], "invalid")
        self.assertEqual(report["source_advisories"]["hints"][0]["line"], 1)

    def test_source_paths_count_size_encoding_and_links_are_bounded(self):
        source = self.source("#define PAGE_SIZE 4096\n")
        self.aar()
        for value in ("../escape.cpp", str(source.resolve()), "app/../pages.cpp", "app\\pages.cpp", "C:pages.cpp", ".", "missing.cpp"):
            with self.subTest(value=value):
                self.report(2, "invalid", "--source-file", value)
        source.write_bytes(b"x" * (1024 * 1024 + 1))
        self.report(2, "invalid", "--source-file", source.relative_to(self.root).as_posix())
        source.write_bytes(b"\xff")
        self.report(2, "invalid", "--source-file", source.relative_to(self.root).as_posix())
        result = self.report(2, "invalid", *[part for i in range(101) for part in ("--source-file", f"{i}.cpp")])
        self.assertEqual(result["source_advisories"]["files"], [])
        link = self.root / "link.cpp"
        self.symlink(link, source)
        self.report(2, "invalid", "--source-file", "link.cpp")

    def test_source_summary_keeps_review_limit_and_hash(self):
        self.source("#define PAGE_SIZE 4096\n")
        self.aar(entries={})
        output = self.folder / "evidence"
        report = self.report(0, "pass", "--source-file", "app/src/main/cpp/pages.cpp", "--output-dir", output)
        markdown = (output / "report.md").read_text(encoding="utf-8")
        self.assertIn("advisory", markdown)
        self.assertIn("not proof", markdown)
        self.assertIn(report["source_advisories"]["files"][0]["sha256"], markdown)
        self.assertIn("No 64-bit ELF alignment", markdown)


    def test_source_output_limit_and_parent_link_are_invalid(self):
        source = self.source("#define PAGE_SIZE 4096\n" * 2001)
        report = self.report(2, "invalid", "--source-file", "app/src/main/cpp/pages.cpp")
        self.assertEqual(len(report["source_advisories"]["hints"]), 2000)
        self.assertIn("2000-result limit", report["source_advisories"]["errors"][0]["error"])
        self.symlink(self.root / "cpp-alias", source.parent, directory=True)
        report = self.report(2, "invalid", "--source-file", "cpp-alias/pages.cpp")
        self.assertEqual(report["source_advisories"]["files"], [])

    def test_sorted_source_paths_and_duplicate_requests_are_deterministic(self):
        self.source("#define PAGE_SIZE 4096\n", "z.cpp")
        self.source("char buffer[4096];\n", "a.cpp")
        args = ("--source-file", "z.cpp", "--source-file", "a.cpp", "--source-file", "z.cpp")
        report = self.report(3, "no_matches", *args)
        self.assertEqual([item["source"] for item in report["source_advisories"]["files"]], ["a.cpp", "z.cpp"])
        self.assertEqual(len(report["source_advisories"]["hints"]), 1)
        self.assertEqual(self.command(*args).stdout, self.command(*args).stdout)
