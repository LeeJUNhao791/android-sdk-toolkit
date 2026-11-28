"""Bounded, advisory C/C++ page-size source hints; never a semantic proof."""

import hashlib
import re
import stat
from pathlib import PurePosixPath


MAX_FILES = 100
MAX_BYTES = 1024 * 1024
MAX_HINTS = 2000
SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"}
# Blank literals/comments but preserve line positions. This is deliberately not a C++ parser.
IGNORED = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
SIZE = r"(?:4096|0x1000)(?:[uUlL]*)(?![\w.])"
DEFINITION = re.compile(r"(?:#\s*define\s+(?:PAGE_SIZE|PAGESIZE)\s+\(?\s*" + SIZE
                        + r"|\b(?:const|constexpr)\b[^;=\n]*\b(?:PAGE_SIZE|PAGESIZE)\s*=\s*\(?\s*" + SIZE + r")", re.I)
CONTEXT = re.compile(r"\b\w*(?:page|align)\w*\b", re.I)
ALIGNMENT = re.compile(r"(?:[/%]\s*" + SIZE + r"|&\s*~\s*\(?\s*(?:4095|0xfff)(?:[uUlL]*)(?![\w.]))", re.I)


def scan_sources(root, paths):
    report = {"status": "no_hints", "files": [], "hints": [], "errors": []}
    if len(paths) > MAX_FILES:
        report.update(status="invalid", errors=[{"source": ".", "error": "At most 100 source files are allowed."}])
        return report
    for relative in sorted(set(paths)):
        try:
            name = PurePosixPath(relative)
            if (not relative or "\\" in relative or ":" in relative or name.is_absolute()
                    or any(part in {"", ".", ".."} for part in relative.split("/"))
                    or name.suffix.lower() not in SUFFIXES):
                raise ValueError("Expected a project-relative C/C++ file without parent segments.")
            path = root
            for part in name.parts:
                path = path / part
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise ValueError("Source symlinks and reparse points are not followed.")
            if root not in path.resolve().parents or not stat.S_ISREG(info.st_mode):
                raise ValueError("Source must be a regular file within the project.")
            with path.open("rb") as stream:
                payload = stream.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise ValueError("Source file exceeds 1 MiB.")
            report["files"].append({"source": relative, "sha256": hashlib.sha256(payload).hexdigest()})
            text = payload.decode("utf-8")
            code = IGNORED.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), text)
            for number, line in enumerate(code.splitlines(), 1):
                for statement in line.split(";"):
                    rule = "page_size_definition" if DEFINITION.search(statement) else None
                    if rule is None and CONTEXT.search(statement) and ALIGNMENT.search(statement):
                        rule = "page_alignment_literal"
                    if rule:
                        if len(report["hints"]) >= MAX_HINTS:
                            raise ValueError("Source hints exceed the 2000-result limit; select fewer files.")
                        report["hints"].append({"source": relative, "line": number, "rule": rule})
        except (OSError, ValueError, RuntimeError) as error:
            report["errors"].append({"source": relative, "error": str(error)})
    report["status"] = "invalid" if report["errors"] else "hints" if report["hints"] else "no_hints"
    return report
