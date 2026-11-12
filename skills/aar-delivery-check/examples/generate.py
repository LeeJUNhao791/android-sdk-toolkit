"""Make small archive fixtures for checking AAR entry names."""

import argparse
from pathlib import Path
from zipfile import ZipFile, ZipInfo


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    entries = {
        "AndroidManifest.xml": '<manifest package="example.device"/>',
        "jni/arm64-v8a/libdevice.so": "fixture placeholder",
        "jni/x86_64/libdevice.so": "fixture placeholder",
        "proguard.txt": "-keep class example.device.DeviceSdk { *; }",
    }
    for name, omitted in (
        ("complete.aar", None),
        ("missing-x86_64.aar", "jni/x86_64/libdevice.so"),
        ("missing-r8-rules.aar", "proguard.txt"),
    ):
        with ZipFile(output / name, "w") as archive:
            for entry, content in entries.items():
                if entry != omitted:
                    archive.writestr(ZipInfo(entry), content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
