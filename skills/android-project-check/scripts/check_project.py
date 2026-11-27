#!/usr/bin/env python3
"""Inventory local Android/UTS AARs and check their native ELF alignment."""

import argparse
import json
import runpy
import stat
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile


SKILLS = Path(__file__).resolve().parents[2]
AAR = runpy.run_path(str(SKILLS / "aar-delivery-check/scripts/check_aar.py"))
APK = runpy.run_path(str(SKILLS / "apk-page-size-check/scripts/check_apk.py"))
SCOPE = ["app/libs/*.aar", "uni_modules/*/utssdk/app-android/libs/*.aar"]
EXIT_CODES = {"pass": 0, "fail": 1, "invalid": 2, "no_matches": 3}


def is_link(path):
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def discover(root, errors):
    def directory(path):
        current = root
        for part in path.relative_to(root).parts:
            current = current / part
            try:
                if is_link(current):
                    raise ValueError("Symlinks and junctions below the project root are not followed.")
                if not current.is_dir():
                    raise ValueError("Expected a directory.")
            except FileNotFoundError:
                return False
        return True

    def children(path):
        try:
            return sorted(path.iterdir(), key=lambda item: item.name) if directory(path) else []
        except (OSError, ValueError) as error:
            errors.append({"source": path.relative_to(root).as_posix(), "error": str(error)})
            return []

    folders = [root / "app/libs"]
    for module in children(root / "uni_modules"):
        try:
            if is_link(module):
                raise ValueError("Symlinks and junctions below the project root are not followed.")
            if module.is_dir():
                folders.append(module / "utssdk/app-android/libs")
        except (OSError, ValueError) as error:
            errors.append({"source": module.relative_to(root).as_posix(), "error": str(error)})
    paths = []
    for folder in folders:
        for path in children(folder):
            if path.suffix.lower() != ".aar":
                continue
            try:
                if is_link(path):
                    raise ValueError("Symlinks and junctions below the project root are not followed.")
                if path.is_file():
                    paths.append(path)
            except (OSError, ValueError) as error:
                errors.append({"source": path.relative_to(root).as_posix(), "error": str(error)})
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def check_native(archive, entry, digest):
    abi = entry.filename.split("/")[1]
    check = AAR["check_abi"](archive, entry.filename, abi)
    result = {"entry": entry.filename, "abi": abi, "sha256": digest,
              "detected_abi": check["detected_abi"], "abi_status": check["status"],
              "elf_alignment": "not_applicable"}
    if abi not in AAR["ELF_ABIS"] or check["detected_abi"] is None:
        result.update(elf_alignment="invalid", error="Invalid or unsupported Android ELF header/ABI.")
    elif check["detected_abi"] in APK["ELF64_MACHINES"]:
        try:
            with archive.open(entry) as native:
                issues = APK["check_load_segments"](
                    native, entry.file_size, APK["ELF64_MACHINES"][check["detected_abi"]],
                )
            result.update(elf_alignment="fail" if issues else "pass", load_issues=issues)
        except APK["INPUT_ERRORS"] as error:
            result.update(elf_alignment="invalid", error=str(error))
    return result


def check_aar(path, root, expected_abis):
    result = {"source": path.relative_to(root).as_posix(), "sha256": None, "status": "pass",
              "manifest_present": False, "abis": [], "missing_abis": [],
              "elf64_count": 0, "libraries": [], "errors": []}
    try:
        with path.open("rb") as stream:
            result["sha256"] = APK["stream_sha256"](stream)
            stream.seek(0)
            with ZipFile(stream) as archive:
                entries = archive.infolist()
                seen = set()
                for entry in entries:
                    name = entry.filename
                    if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED):
                        raise ValueError("Unsupported AAR ZIP compression method: " + name)
                    if (name in seen or "\\" in name or ":" in name.split("/")[0]
                            or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))):
                        raise ValueError("Duplicate or unsafe AAR member: " + name)
                    seen.add(name)
                files = [entry for entry in entries if not entry.is_dir()]
                result["manifest_present"] = AAR["MANIFEST"] in {entry.filename for entry in files}
                if not result["manifest_present"]:
                    raise ValueError("Missing AndroidManifest.xml.")
                for entry in sorted(files, key=lambda item: item.filename):
                    with archive.open(entry) as member:
                        digest = APK["stream_sha256"](member)
                    if entry.filename.startswith("jni/") and entry.filename.endswith(".so"):
                        if len(entry.filename.split("/")) != 3:
                            raise ValueError("Expected jni/<abi>/<library>.so: " + entry.filename)
                        result["libraries"].append(check_native(archive, entry, digest))
        result["abis"] = sorted({item["abi"] for item in result["libraries"]})
        result["missing_abis"] = sorted(set(expected_abis) - set(result["abis"]))
        result["elf64_count"] = sum(item["detected_abi"] in APK["ELF64_MACHINES"]
                                    for item in result["libraries"])
        if any(item["elf_alignment"] == "invalid" for item in result["libraries"]):
            result["status"] = "invalid"
        elif result["missing_abis"] or any(
                item["abi_status"] != "pass" or item["elf_alignment"] == "fail"
                for item in result["libraries"]):
            result["status"] = "fail"
    except APK["INPUT_ERRORS"] as error:
        result["status"] = "invalid"
        result["errors"].append(str(error))
    return result


def scan(root, expected_abis):
    report = {"status": "no_matches", "scope": SCOPE, "expected_abis": expected_abis,
              "artifacts": [], "errors": []}
    try:
        if not root.is_dir():
            raise ValueError("Project root must be an existing directory.")
        report["artifacts"] = [check_aar(path, root, expected_abis)
                               for path in discover(root, report["errors"])]
    except (OSError, ValueError) as error:
        report["errors"].append({"source": ".", "error": str(error)})
    statuses = {item["status"] for item in report["artifacts"]}
    if report["errors"] or "invalid" in statuses:
        report["status"] = "invalid"
    elif statuses:
        report["status"] = "fail" if "fail" in statuses else "pass"
    return report


def render_summary(report):
    lines = ["# Android project AAR check", "", "## English", "",
             "Status: " + report["status"], "",
             "Local AAR inspection only. AAR ZIP layout is not APK ZIP alignment. "
             "Final APK packaging and device/JNI execution require separate verification.", "",
             "Manifest: presence/readability only. Native scope: jni/<abi>/*.so. "
             "Explicit ABI expectations apply to every AAR, including Java-only AARs.", "",
             "## 简体中文", "", "状态：" + report["status"], "",
             "仅检查本地 AAR。AAR ZIP 布局不能作为 APK ZIP 对齐结论；"
             "最终 APK 打包及设备/JNI 运行需单独验证。", "",
             "Manifest 仅检查存在且可读取；原生库范围为 jni/<abi>/*.so。"
             "显式 ABI 要求适用于每个 AAR，包括纯 Java AAR。", ""]
    if report["status"] == "no_matches":
        lines += ["No matching AARs; this is not a pass. / 没有匹配的 AAR，不代表检查通过。", ""]
    for artifact in report["artifacts"]:
        lines += ["### " + artifact["source"], "",
                  "- Status / 状态: " + artifact["status"],
                  "- AAR SHA-256: " + str(artifact["sha256"]),
                  "- Manifest present / Manifest 存在: " + str(artifact["manifest_present"]),
                  "- ABIs: " + (", ".join(artifact["abis"]) or "none / 无"),
                  "- Missing expected ABIs / 缺少约定 ABI: " + (", ".join(artifact["missing_abis"]) or "none / 无")]
        if not artifact["elf64_count"]:
            lines += ["- No 64-bit ELF alignment was evaluated. / 未检查 64 位 ELF 对齐。"]
        for native in artifact["libraries"]:
            lines += ["", "- " + native["entry"],
                      "  - SO SHA-256: " + native["sha256"],
                      "  - ABI: " + native["abi_status"] + "; detected / 检测: " + str(native["detected_abi"]),
                      "  - ELF PT_LOAD alignment / 对齐: " + native["elf_alignment"]]
            if native.get("load_issues"):
                lines += ["  - PT_LOAD: " + json.dumps(native["load_issues"], sort_keys=True)]
            if native.get("error"):
                lines += ["  - Error / 错误: " + native["error"]]
        lines += ["- Error / 错误: " + error for error in artifact["errors"]]
        lines.append("")
    lines += ["- " + error["source"] + ": " + error["error"] for error in report["errors"]]
    lines += ["", "For failures, ask the supplier to verify the listed AAR/SO hashes, ABI and PT_LOAD values. "
              "For invalid input, resolve the reported input error before interpreting alignment.", "",
              "失败时请供应商核对上述 AAR/SO 摘要、ABI 和 PT_LOAD 数值；"
              "输入无效时先处理输入错误，再解读对齐结果。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--expect-abi", action="append", default=[], choices=sorted(AAR["ELF_ABIS"]),
                        help="Require this ABI in EVERY AAR (including Java-only); repeatable, no default.")
    parser.add_argument("--output-dir", type=Path, help="New directory OUTSIDE project for JSON and bilingual Markdown.")
    args = parser.parse_args()
    try:
        root = args.project_root.resolve()
        if args.output_dir is not None:
            output = args.output_dir.resolve()
            if output == root or root in output.parents:
                raise ValueError("The output directory must be outside the project root.")
            if args.output_dir.exists() or args.output_dir.is_symlink():
                raise ValueError("Choose a new output directory; existing paths are preserved.")
            args.output_dir = output
            args.output_dir.mkdir(parents=True)
    except (OSError, ValueError, RuntimeError) as error:
        print("Project check output directory error: " + str(error), file=sys.stderr)
        return 2
    report = scan(root, sorted(set(args.expect_abi)))
    content = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(content, end="")
    if args.output_dir is not None:
        try:
            with (args.output_dir / "report.json").open("x", encoding="utf-8") as stream:
                stream.write(content)
            with (args.output_dir / "report.md").open("x", encoding="utf-8") as stream:
                stream.write(render_summary(report))
        except (OSError, ValueError) as error:
            print("Project check output error: " + str(error), file=sys.stderr)
            return 2
    return EXIT_CODES[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
