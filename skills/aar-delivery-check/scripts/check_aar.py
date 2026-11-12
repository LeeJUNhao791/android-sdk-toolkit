#!/usr/bin/env python3
"""Check Android AAR entries against a delivery contract."""

import argparse
import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile


MANIFEST = "AndroidManifest.xml"
ELF_ABIS = {
    "armeabi-v7a": (1, 40),
    "arm64-v8a": (2, 183),
    "x86": (1, 3),
    "x86_64": (2, 62),
}
ABI_BY_ELF = {header: abi for abi, header in ELF_ABIS.items()}


def load_expected(path):
    contract = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(contract, dict):
        raise ValueError("The contract must be a JSON object.")
    unknown = contract.keys() - {"native_libraries", "required_entries"}
    if unknown:
        raise ValueError("Unknown contract fields: " + ", ".join(sorted(unknown)))

    libraries = contract.get("native_libraries", {})
    entries = contract.get("required_entries", [])
    if not isinstance(libraries, dict) or not isinstance(entries, list):
        raise ValueError("native_libraries must be an object and required_entries must be an array.")
    expected = [MANIFEST]
    native_entries = {}
    for name, abis in libraries.items():
        if not name.startswith("lib") or not name.endswith(".so") or "/" in name or "\\" in name:
            raise ValueError(f"Expected a native library filename, got {name!r}.")
        if not isinstance(abis, list) or not abis or any(
            not isinstance(abi, str) or abi not in ELF_ABIS for abi in abis
        ):
            raise ValueError(f"Expected a non-empty list of Android ABIs for {name!r}.")
        native_entries.update((f"jni/{abi}/{name}", abi) for abi in abis)
    expected.extend(native_entries)
    for entry in entries:
        if (
            not isinstance(entry, str) or "\\" in entry
            or any(part in {"", ".", ".."} for part in entry.split("/"))
        ):
            raise ValueError(f"Expected a relative AAR file path, got {entry!r}.")
        expected.append(entry)
    return list(dict.fromkeys(expected)), native_entries


def check_abi(archive, entry, expected):
    with archive.open(entry) as native:
        header = native.read(20)
    report = {"entry": entry, "expected_abi": expected, "detected_abi": None}
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] not in (1, 2):
        return {**report, "status": "invalid_elf_header"}
    if header[5] != 1:
        return {**report, "status": "unsupported_elf_endianness"}
    machine = int.from_bytes(header[18:20], "little")
    detected = ABI_BY_ELF.get((header[4], machine))
    return {
        **report,
        "detected_abi": detected,
        "elf_class": header[4],
        "elf_machine": machine,
        "status": "pass" if detected == expected else "abi_mismatch",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aar", type=Path)
    parser.add_argument("--expect", type=Path, required=True, help="JSON delivery contract.")
    parser.add_argument("--verify-abi", action="store_true", help="Check ELF headers of required native libraries.")
    args = parser.parse_args()
    try:
        if args.aar.suffix.lower() != ".aar":
            raise ValueError("Input must be an .aar file.")
        expected, native_entries = load_expected(args.expect)
        abi_checks = []
        with ZipFile(args.aar) as archive:
            present = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
            if MANIFEST not in present:
                raise ValueError(f"Invalid AAR: missing {MANIFEST}.")
            if args.verify_abi:
                abi_checks = [
                    check_abi(archive, entry, abi)
                    for entry, abi in native_entries.items() if entry in present
                ]
    except (OSError, ValueError, BadZipFile, RuntimeError) as error:
        print(f"AAR check error: {error}", file=sys.stderr)
        return 2

    missing = [entry for entry in expected if entry not in present]
    failed = bool(missing) or any(item["status"] != "pass" for item in abi_checks)
    report = {
        "status": "fail" if failed else "pass",
        "checks": [{"entry": entry, "present": entry in present} for entry in expected],
        "missing_entries": missing,
    }
    if args.verify_abi:
        report["abi_checks"] = abi_checks
    print(json.dumps(report, indent=2))
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
