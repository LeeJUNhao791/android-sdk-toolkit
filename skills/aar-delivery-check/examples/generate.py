"""Make small archive fixtures with representative ELF headers."""

import argparse
import struct
from pathlib import Path
from zipfile import ZipFile, ZipInfo


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    arm = "jni/arm64-v8a/libdevice.so"
    x86 = "jni/x86_64/libdevice.so"
    entries = {
        "AndroidManifest.xml": '<manifest package="example.device"/>',
        arm: struct.pack("<4sBBB9xHH", b"\x7fELF", 2, 1, 1, 3, 183),
        x86: struct.pack("<4sBBB9xHH", b"\x7fELF", 2, 1, 1, 3, 62),
        "proguard.txt": "-keep class example.device.DeviceSdk { *; }",
    }
    for name, omitted in (
        ("complete.aar", None),
        ("missing-x86_64.aar", x86),
        ("missing-r8-rules.aar", "proguard.txt"),
        ("wrong-abi.aar", None),
    ):
        with ZipFile(output / name, "w") as archive:
            for entry, content in entries.items():
                if entry != omitted:
                    if name == "wrong-abi.aar" and entry == arm:
                        content = entries[x86]
                    archive.writestr(ZipInfo(entry), content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
