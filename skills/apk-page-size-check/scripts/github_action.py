"""Run the existing APK checker and publish its report to GitHub Actions."""

import html
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def cell(value):
    text = html.escape(str(value)).replace("|", "&#124;").replace("`", "&#96;")
    return "<code>" + text.replace("\r", "").replace("\n", "<br>") + "</code>"


def summary(report):
    lines = ["## APK 16 KB alignment", "", "Result **" + report["status"] + "**", "",
             "APK " + cell(report["apk"]), ""]
    for key in ("detail", "error"):
        if key in report:
            lines.extend([cell(report[key]), ""])
    provenance = report.get("native_provenance")
    if provenance:
        lines.extend(["Gradle provenance for " + cell(provenance["variant"]) + " · "
                      + cell(provenance["status"]), ""])
    if report["libraries"]:
        lines.extend(["| Library | ELF | ZIP | Origin | Candidate coordinates |",
                      "| --- | --- | --- | --- | --- |"])
        for library in report["libraries"]:
            origin = library.get("origin", {})
            coordinates = "<br>".join(cell(candidate["coordinate"])
                                      for candidate in origin.get("candidates", [])) or "-"
            status = origin.get("status", "not_requested")
            if origin.get("method"):
                status += " (" + origin["method"] + ")"
            values = [library["entry"], library["elf"], library["zip"], status]
            lines.append("| " + " | ".join(map(cell, values)) + " | " + coordinates + " |")
        lines.append("")
    if any(row["zip"] == "fail" and row["elf"] in ("pass", "not_applicable") for row in report["libraries"]):
        lines.extend(["For ZIP-only failures, check APK packaging and ZIP alignment. "
                      "Candidate coordinates list matching AAR entries.", ""])
    lines.extend([
        "Candidate matches use SHA-256 within the supplied AAR list. "
        "Multiple matches and unknown origins remain explicit. "
        "Supply `aar-manifest` to request candidate matching.", "",
        "Static alignment checks cover this APK. Installation and JNI execution "
        "on a 16 KB device require runtime validation.", "",
    ])
    return "\n".join(lines)


def main():
    workspace = Path(os.environ["GITHUB_WORKSPACE"])
    command = [sys.executable, str(Path(__file__).with_name("check_apk.py")),
               str((workspace / os.environ["INPUT_APK"]).resolve())]
    manifest = os.environ.get("INPUT_AAR_MANIFEST", "")
    if manifest:
        command.extend(["--aar-manifest", str((workspace / manifest).resolve())])
    provenance = os.environ.get("INPUT_NATIVE_PROVENANCE", "")
    if provenance:
        command.extend(["--native-provenance", str((workspace / provenance).resolve())])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    report = json.loads(result.stdout)
    directory = Path(tempfile.mkdtemp(prefix="apk-16kb-", dir=os.environ["RUNNER_TEMP"]))
    report_path = directory / "report.json"
    report_path.write_text(result.stdout, encoding="utf-8")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
        stream.write(summary(report))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
        stream.write(f"status={report['status']}\nreport={report_path}\nexit-code={result.returncode}\n")
    print("APK 16 KB check returned " + report["status"])
    return 0 if result.returncode == 3 else result.returncode


if __name__ == "__main__":
    sys.exit(main())
