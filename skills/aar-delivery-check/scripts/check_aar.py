#!/usr/bin/env python3
"""Check Android AAR entries against a delivery contract."""

import argparse
import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile


MANIFEST = "AndroidManifest.xml"
ABIS = {"armeabi-v7a", "arm64-v8a", "x86", "x86_64"}


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
    for name, abis in libraries.items():
        if not name.startswith("lib") or not name.endswith(".so") or "/" in name or "\\" in name:
            raise ValueError(f"Expected a native library filename, got {name!r}.")
        if not isinstance(abis, list) or not abis or any(
            not isinstance(abi, str) or abi not in ABIS for abi in abis
        ):
            raise ValueError(f"Expected a non-empty list of Android ABIs for {name!r}.")
        expected.extend(f"jni/{abi}/{name}" for abi in abis)
    for entry in entries:
        if (
            not isinstance(entry, str) or "\\" in entry
            or any(part in {"", ".", ".."} for part in entry.split("/"))
        ):
            raise ValueError(f"Expected a relative AAR file path, got {entry!r}.")
        expected.append(entry)
    return list(dict.fromkeys(expected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aar", type=Path)
    parser.add_argument("--expect", type=Path, required=True, help="JSON delivery contract.")
    args = parser.parse_args()
    try:
        if args.aar.suffix.lower() != ".aar":
            raise ValueError("Input must be an .aar file.")
        expected = load_expected(args.expect)
        with ZipFile(args.aar) as archive:
            present = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
        if MANIFEST not in present:
            raise ValueError(f"Invalid AAR: missing {MANIFEST}.")
    except (OSError, ValueError, BadZipFile) as error:
        print(f"AAR check error: {error}", file=sys.stderr)
        return 2

    missing = [entry for entry in expected if entry not in present]
    print(json.dumps({
        "status": "fail" if missing else "pass",
        "checks": [{"entry": entry, "present": entry in present} for entry in expected],
        "missing_entries": missing,
    }, indent=2))
    return int(bool(missing))


if __name__ == "__main__":
    sys.exit(main())
