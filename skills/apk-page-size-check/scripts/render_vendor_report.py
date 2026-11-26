#!/usr/bin/env python3
"""Render a bilingual Markdown draft from the Toolkit's APK 16 KB checker JSON."""

import argparse
import json
import re
import runpy
import sys
from pathlib import Path

_checker = runpy.run_path(str(Path(__file__).with_name("check_apk.py")))
ABI32 = _checker["ABI32"]
ELF64_MACHINES = _checker["ELF64_MACHINES"]
PAGE_SIZE = _checker["PAGE_SIZE"]


COORDINATE = r"(?![A-Za-z]:)[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.-]*:[A-Za-z0-9][A-Za-z0-9_.+-]*"
SHA256 = r"[0-9a-f]{64}"
GITHUB_TOKEN = r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{36,}"


def safe_text(value, pattern):
    return (isinstance(value, str) and re.fullmatch(pattern, value) is not None
            and re.search(GITHUB_TOKEN, value) is None)


def uint64(value):
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError
    return value


def elf_follow_up(origin, apk_entry, provenance, evidence):
    status = origin.get("status")
    matches = origin.get("candidates")
    digest = origin.get("sha256")
    if safe_text(digest, SHA256):
        evidence.append(f"- APK SO SHA-256 / APK 内 SO SHA-256 `{digest}`")

    candidate = matches[0] if (status == "single_candidate" and isinstance(matches, list)
                               and len(matches) == 1) else None
    if isinstance(candidate, dict) and apk_entry and safe_text(digest, SHA256):
        member = "jni/" + apk_entry[4:]
        coordinate = candidate.get("coordinate")
        method = origin.get("method")
        merged = origin.get("merged_sha256")
        direct_match = ("merged_sha256" not in origin
                        and (method == "direct_sha256" or ("method" not in origin and provenance is None)))
        strip_chain = (method == "gradle_strip_chain" and isinstance(provenance, dict)
                       and provenance.get("status") == "verified"
                       and safe_text(merged, SHA256) and merged != digest)
        if (candidate.get("entry") == member and safe_text(coordinate, COORDINATE)
                and (direct_match or strip_chain)):
            evidence.extend([
                f"- Single AAR candidate / 唯一 AAR 候选 `{coordinate}`",
                f"- AAR member / AAR 条目 `{member}`",
            ])
            if strip_chain:
                evidence.append(f"- Pre-strip SO SHA-256 / 剥离符号前 SO SHA-256 `{merged}`")
                return (
                    "**复查 AAR ELF**。APK 内 SO 的 16 KB ELF 对齐失败。"
                    "检查器验证了同一次 Gradle 构建的符号剥离链，并用剥离前的 SO 匹配 AAR 条目。"
                    "请复查该条目的 ELF 对齐。若也失败，请向供应商索取支持 16 KB ELF 对齐的版本。"
                    "若通过，请检查符号剥离和后续打包。",
                    "**Verify AAR ELF.** The APK SO failed 16 KB ELF alignment. The checker's verified same-build "
                    "Gradle strip chain matched the pre-strip SO to the AAR member. Check that member's ELF alignment. "
                    "If that member also fails, ask the supplier for a 16 KB-aligned version. "
                    "If it passes, investigate stripping and packaging.",
                )
            return (
                "**供应商跟进**。16 KB ELF 对齐失败。在所提供的 AAR 中找到一个候选。"
                "APK 内 SO 与 AAR 条目的 SHA-256 一致。请确认支持 16 KB ELF 对齐的版本，或提供重编译的 AAR。",
                "**Supplier follow-up.** 16 KB ELF alignment failed. One candidate matched among the supplied AARs. "
                "The APK SO matched the AAR member by direct SHA-256. "
                "Please confirm a supported version with 16 KB ELF alignment or provide a rebuilt AAR.",
            )

    if status == "multiple_candidates":
        reason_zh = "多个 AAR 候选匹配。"
        reason_en = "Multiple supplied AAR candidates matched."
    else:
        reason_zh = "可共享证据尚未确认唯一 AAR 候选。"
        reason_en = "The shareable evidence does not establish a single AAR candidate."
    return (
        f"**补充证据**。16 KB ELF 对齐失败。{reason_zh}请核对同一变体实际解析到的依赖，必要时补充同次构建的溯源。",
        f"**More evidence needed.** 16 KB ELF alignment failed. {reason_en} "
        "Check the variant's resolved dependencies and collect same-build provenance if needed.",
    )


def render(report):
    if report["page_size"] != PAGE_SIZE or not isinstance(report["libraries"], list):
        raise ValueError
    provenance = report.get("native_provenance")
    zh, en, evidence = [], [], []
    failed = has_64_bit = False
    for library in report["libraries"]:
        abi, name, elf, zip_result = (library[key] for key in ("abi", "entry", "elf", "zip"))
        if abi not in ELF64_MACHINES and abi not in ABI32:
            raise ValueError
        elf_statuses = ("pass", "fail") if abi in ELF64_MACHINES else ("not_applicable",)
        if elf not in elf_statuses or zip_result not in ("pass", "fail", "compressed"):
            raise ValueError
        has_64_bit |= abi in ELF64_MACHINES
        failed |= "fail" in (elf, zip_result)

        entry = name if safe_text(name, rf"lib/{re.escape(abi)}/[A-Za-z0-9_][A-Za-z0-9_.+-]*[.]so") else None
        label = f"`{entry}`" if entry else "(entry name omitted / 条目名已省略)"
        evidence.extend(["", f"### {label}", "", f"- ABI `{abi}` · ELF `{elf}` · ZIP `{zip_result}`"])
        if zip_result != "compressed":
            offset = uint64(library["zip_data_offset"])
            evidence.append(f"- ZIP data offset / ZIP 数据起点 `{offset}`")

        if elf == "fail":
            issues = library["load_issues"]
            if not isinstance(issues, list) or not issues:
                raise ValueError
            for issue in issues:
                index, align, offset, vaddr = (uint64(issue[field]) for field in (
                    "program_header", "p_align", "p_offset", "p_vaddr",
                ))
                evidence.append(f"- Failing PT_LOAD / 未通过的加载段 #{index} "
                                f"`p_align={align}, p_offset={offset}, p_vaddr={vaddr}`")
            origin = library.get("origin")
            zh_action, en_action = elf_follow_up(
                origin if isinstance(origin, dict) else {}, entry, provenance, evidence,
            )
            zh.append(f"- {label} {zh_action}")
            en.append(f"- {label} {en_action}")
        if zip_result == "fail":
            zh.append(f"- {label} **应用打包**。修正未压缩 SO 在 APK 内的 ZIP 对齐，复查最终 APK。")
            en.append(f"- {label} **App packaging.** Fix APK ZIP alignment for the uncompressed SO and recheck the final APK.")

    expected = "fail" if failed else "pass" if has_64_bit else "not_applicable"
    if report["status"] != expected:
        raise ValueError
    if not has_64_bit:
        zh.append("- APK 中没有 ARM64 或 x86-64 原生库可供 ELF 检查。")
        en.append("- No ARM64 or x86-64 libraries were available for ELF checks.")
    if expected == "pass":
        zh.append("- 适用的对齐检查均通过。")
        en.append("- Applicable checks passed.")
    return "\n".join([
        "# Android 16 KB alignment / Android 16 KB 对齐",
        "",
        "APK 静态检查。安装和 JNI 运行需单独验证。",
        "APK static checks. Verify installation and JNI execution separately.",
        "",
        "## 中文处理建议", "", *zh,
        "", "## English triage", "", *en,
        *(["", "## Evidence / 可共享证据", *evidence] if evidence else []),
        "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JSON from check_apk.py.")
    parser.add_argument("-o", "--output", type=Path, help="New Markdown file. Defaults to UTF-8 stdout.")
    args = parser.parse_args()
    try:
        document = render(json.loads(args.report.read_bytes())).encode("utf-8")
    except (KeyError, OSError, RecursionError, TypeError, ValueError):
        print("Expected valid 16 KB checker JSON with usable alignment results.", file=sys.stderr)
        return 2

    try:
        if args.output is None:
            sys.stdout.buffer.write(document)
        else:
            with args.output.open("xb") as file:
                file.write(document)
    except OSError:
        print("Could not write the Markdown report. Choose a writable, new output file.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
