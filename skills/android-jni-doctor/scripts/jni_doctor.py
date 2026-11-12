#!/usr/bin/env python3
"""Match an Android JNI load error to evidence in an APK."""

import argparse
import json
import re
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile


ELF_ABIS = {
    "armeabi-v7a": (1, 40),
    "arm64-v8a": (2, 183),
    "x86": (1, 3),
    "x86_64": (2, 62),
}
LIBRARY = r"lib[A-Za-z0-9_.+-]+\.so"
MISSING = re.compile(rf"""(?:library ["']({LIBRARY})["'] not found|couldn't find ["']({LIBRARY})["'])""")


def diagnose(archive, abi, log, library):
    report = {"kind": "undetermined", "abi": abi}
    if "UnsatisfiedLinkError" not in log:
        return {**report, "detail": "No UnsatisfiedLinkError found in the supplied log."}
    missing = MISSING.search(log)
    if missing:
        library = missing.group(1) or missing.group(2)
    if library:
        entry = f"lib/{abi}/{library}"
        report.update(library=library, entry=entry)
        try:
            with archive.open(entry) as native:
                header = native.read(20)
        except KeyError:
            if missing:
                return {
                    **report, "kind": "library_absent_from_apk", "evidence": "apk_and_log",
                    "detail": "The reported library is absent for this ABI in the supplied APK.",
                }
        else:
            if len(header) < 20 or header[:4] != b"\x7fELF" or header[5] not in (1, 2):
                return {**report, "kind": "invalid_elf_header", "evidence": "apk"}
            elf_class = header[4]
            machine = int.from_bytes(header[18:20], "little" if header[5] == 1 else "big")
            expected_class, expected_machine = ELF_ABIS[abi]
            if (elf_class, machine) != (expected_class, expected_machine):
                return {
                    **report, "kind": "abi_mismatch", "evidence": "apk",
                    "elf_class": elf_class, "elf_machine": machine,
                    "expected_elf_class": expected_class, "expected_elf_machine": expected_machine,
                }
    if "No implementation found for" in log:
        return {
            **report, "kind": "jni_binding_failure", "evidence": "log",
            "detail": "Check the Java declaration and JNI registration or exported method name.",
        }
    return {
        **report, "detail": "Check the installed splits, loader dependencies and JNI registration.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--abi", choices=ELF_ABIS, required=True)
    parser.add_argument("--log", type=Path, required=True, help="Log from the failing app run.")
    parser.add_argument("--library", help="Native filename to inspect when the log lacks one.")
    args = parser.parse_args()
    try:
        if args.apk.suffix.lower() != ".apk":
            raise ValueError("Input must be an .apk file.")
        if args.library and not re.fullmatch(LIBRARY, args.library):
            raise ValueError("--library must be a filename such as libdevice.so.")
        log = args.log.read_text(encoding="utf-8-sig")
        with ZipFile(args.apk) as archive:
            if "AndroidManifest.xml" not in archive.namelist():
                raise ValueError("Invalid APK: missing AndroidManifest.xml.")
            report = diagnose(archive, args.abi, log, args.library)
    except (OSError, ValueError, BadZipFile, RuntimeError, NotImplementedError) as error:
        print(f"JNI diagnosis error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
