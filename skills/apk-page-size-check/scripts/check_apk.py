#!/usr/bin/env python3
"""Check native library LOAD and ZIP alignment in a final APK for 16 KB Android pages."""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile
from zlib import error as ZlibError


PAGE_SIZE = 16 * 1024
ELF64_MACHINES = {"arm64-v8a": 183, "x86_64": 62}
ABI32 = {"armeabi-v7a", "x86"}
ELF64_HEADER = struct.Struct("<16sHHIQQQIHHHHHH")
ELF64_PROGRAM_HEADER = struct.Struct("<II6Q")
ZIP_LOCAL_HEADER = struct.Struct("<4s5H3I2H")
INPUT_ERRORS = (OSError, ValueError, BadZipFile, RuntimeError, EOFError, ZlibError)
EXIT_CODES = {"pass": 0, "fail": 1, "invalid": 2, "not_applicable": 3}


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("Truncated header.")
    return data


def check_load_segments(stream, size, machine):
    header = ELF64_HEADER.unpack(read_exact(stream, ELF64_HEADER.size))
    ident, kind, actual_machine, version, _, phoff, _, _, ehsize, phentsize, phnum, *_ = header
    if (ident[:7] != b"\x7fELF\x02\x01\x01" or kind != 3 or
            version != 1 or actual_machine != machine or ehsize != ELF64_HEADER.size):
        raise ValueError("Expected a little-endian ELF64 shared object for the APK ABI.")
    if (not 0 < phnum < 0xFFFF or phentsize != ELF64_PROGRAM_HEADER.size or
            phoff < ehsize or phoff + phnum * phentsize > size):
        raise ValueError("Invalid or unsupported ELF program header table.")

    stream.seek(phoff)
    loads = 0
    issues = []
    for index in range(phnum):
        phdr = ELF64_PROGRAM_HEADER.unpack(read_exact(stream, phentsize))
        kind, _, offset, address, _, file_size, memory_size, alignment = phdr
        if kind != 1:  # PT_LOAD
            continue
        loads += 1
        if file_size > memory_size or offset + file_size > size:
            raise ValueError(f"PT_LOAD program header {index} has an invalid file range.")
        if (alignment < PAGE_SIZE or alignment & (alignment - 1) or
                (offset - address) % alignment):
            issues.append({
                "program_header": index, "p_align": alignment,
                "p_offset": offset, "p_vaddr": address,
            })
    if not loads:
        raise ValueError("ELF has no PT_LOAD segments.")
    return issues


def data_offset(apk, entry):
    apk.seek(entry.header_offset)
    fields = ZIP_LOCAL_HEADER.unpack(read_exact(apk, ZIP_LOCAL_HEADER.size))
    signature, _, flags, compression, _, _, crc, compressed_size, size, name_length, extra_length = fields
    if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
        raise ValueError("Unsupported APK ZIP compression method.")
    if signature != b"PK\x03\x04" or flags != entry.flag_bits or compression != entry.compress_type:
        raise ValueError("ZIP local header does not match the central directory.")
    if not flags & 8:  # Without a data descriptor, the local sizes and CRC are present.
        if (crc, compressed_size, size) != (entry.CRC, entry.compress_size, entry.file_size):
            raise ValueError("ZIP local header sizes or CRC do not match the central directory.")
    if compression == ZIP_STORED and entry.compress_size != entry.file_size:
        raise ValueError("Stored ZIP entry has inconsistent sizes.")
    return entry.header_offset + ZIP_LOCAL_HEADER.size + name_length + extra_length


def read_to_end(stream):
    while stream.read(1024 * 1024):
        pass


def entry_sha256(archive, entry):
    digest = hashlib.sha256()
    with archive.open(entry) as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_aar_manifest(path):
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or set(manifest) != {"consumer_configuration", "artifacts"}:
        raise ValueError("Expected consumer_configuration and artifacts in the AAR manifest.")
    configuration = manifest["consumer_configuration"]
    if not isinstance(configuration, str) or not configuration.strip():
        raise ValueError("Expected the consumer runtime classpath in consumer_configuration.")
    if not isinstance(manifest["artifacts"], list):
        raise ValueError("Expected an array of resolved AAR artifacts.")

    artifacts = {}
    for artifact in manifest["artifacts"]:
        if not isinstance(artifact, dict) or set(artifact) != {"coordinate", "path"}:
            raise ValueError("Expected coordinate and path for each resolved AAR.")
        coordinate = artifact["coordinate"]
        parts = coordinate.split(":") if isinstance(coordinate, str) else []
        if len(parts) != 3 or any(not part or any(char.isspace() for char in part) for part in parts):
            raise ValueError("Expected a resolved Gradle coordinate in group:module:version form.")
        filename = artifact["path"]
        if not isinstance(filename, str) or Path(filename).suffix.lower() != ".aar":
            raise ValueError("Expected an .aar path for each resolved artifact.")
        aar = (path.parent / filename).resolve()
        artifacts[coordinate, aar] = None
    return configuration, list(artifacts)


def find_aar_origins(artifacts, apk_digests):
    target_entries = {"jni/" + entry[4:]: entry for entry in apk_digests}
    candidates = {entry: [] for entry in apk_digests}
    for coordinate, aar in artifacts:
        try:
            with ZipFile(aar) as archive:
                if "AndroidManifest.xml" not in archive.namelist():
                    raise ValueError("Missing AndroidManifest.xml.")
                seen = set()
                for entry in archive.infolist():
                    apk_entry = target_entries.get(entry.filename)
                    if apk_entry is None:
                        continue
                    if entry.filename in seen:
                        raise ValueError(f"Duplicate AAR entry: {entry.filename}")
                    seen.add(entry.filename)
                    if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                        raise ValueError(f"Unsupported AAR ZIP compression method: {entry.filename}")
                    if entry_sha256(archive, entry) == apk_digests[apk_entry]:
                        candidates[apk_entry].append({
                            "coordinate": coordinate, "aar": str(aar), "entry": entry.filename,
                        })
        except INPUT_ERRORS as error:
            raise ValueError(f"Invalid resolved AAR {aar}: {error}") from error
    return candidates


def annotate_origins(report, manifest_path, digests):
    configuration, artifacts = load_aar_manifest(manifest_path)
    candidates = find_aar_origins(artifacts, digests)
    report["aar_manifest"] = {"path": str(manifest_path), "consumer_configuration": configuration}
    statuses = {0: "unknown", 1: "single_candidate"}
    for library in report["libraries"]:
        entry = library["entry"]
        if entry in candidates:
            matches = candidates[entry]
            library["origin"] = {
                "status": statuses.get(len(matches), "multiple_candidates"),
                "sha256": digests[entry], "candidates": matches,
            }


def check_library(apk, archive, entry, abi):
    result = {"entry": entry.filename, "abi": abi, "elf": "unchecked", "zip": "unchecked"}
    if abi not in ELF64_MACHINES and abi not in ABI32:
        return {**result, "elf": "invalid", "error": "Unsupported Android ABI."}
    try:
        offset = data_offset(apk, entry)
        with archive.open(entry) as native:
            if abi in ELF64_MACHINES:
                try:
                    issues = check_load_segments(native, entry.file_size, ELF64_MACHINES[abi])
                except ValueError as error:
                    result.update(elf="invalid", error=str(error))
                else:
                    result.update(elf="fail" if issues else "pass", load_issues=issues)
            else:
                result["elf"] = "not_applicable"
            # Read the rest of the entry so zipfile checks the native payload's CRC.
            read_to_end(native)
        if entry.compress_type == ZIP_STORED:
            result.update(zip="fail" if offset % PAGE_SIZE else "pass", zip_data_offset=offset)
        else:
            result["zip"] = "compressed"
    except INPUT_ERRORS as error:
        result.pop("load_issues", None)
        result.update(elf="unchecked", zip="invalid", error=str(error))
    return result


def check_apk(path, libraries, digests=None):
    if path.suffix.lower() != ".apk":
        raise ValueError("Input must be an .apk file.")
    with path.open("rb") as apk, ZipFile(apk) as archive:
        entries = archive.infolist()
        manifest = [entry for entry in entries if entry.filename == "AndroidManifest.xml"]
        if len(manifest) != 1 or not manifest[0].file_size:
            raise ValueError("Expected one nonempty AndroidManifest.xml.")
        data_offset(apk, manifest[0])
        with archive.open(manifest[0]) as stream:
            read_to_end(stream)

        seen = set()
        for entry in entries:
            if entry.filename in seen:
                raise ValueError(f"Duplicate APK entry: {entry.filename}")
            seen.add(entry.filename)
            parts = entry.filename.split("/")
            if len(parts) != 3 or parts[0] != "lib" or not parts[2].endswith(".so"):
                continue
            result = check_library(apk, archive, entry, parts[1])
            libraries.append(result)
            if digests is not None and "fail" in (result["elf"], result["zip"]):
                digests[entry.filename] = entry_sha256(archive, entry)

    if any("invalid" in (item["elf"], item["zip"]) for item in libraries):
        return "invalid"
    if any("fail" in (item["elf"], item["zip"]) for item in libraries):
        return "fail"
    if not any(item["abi"] in ELF64_MACHINES for item in libraries):
        return "not_applicable"
    return "pass"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--aar-manifest", type=Path, help="JSON list of resolved consumer AARs and coordinates.")
    args = parser.parse_args()
    report = {"apk": str(args.apk), "page_size": PAGE_SIZE, "libraries": []}
    digests = {} if args.aar_manifest is not None else None
    try:
        report["status"] = check_apk(args.apk, report["libraries"], digests)
        if args.aar_manifest is not None and report["status"] != "invalid":
            annotate_origins(report, args.aar_manifest, digests)
    except INPUT_ERRORS as error:
        report.update(status="invalid", error=str(error))
    if report["status"] == "not_applicable":
        report["detail"] = "No arm64-v8a or x86_64 shared libraries in this APK."
    print(json.dumps(report, indent=2))
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
