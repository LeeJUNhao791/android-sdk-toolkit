"""Generate synthetic APK and AAR archives to demonstrate native origin matching."""

import argparse
import json
import struct
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def generate(output):
    output.mkdir(parents=True, exist_ok=True)
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = struct.pack("<HHIQQQIHHHHHH", 3, 183, 1, 0, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    load = struct.pack("<II6Q", 1, 5, 0, 0, 0, 120, 120, 4096)
    elf = ident + header + load
    dependencies = {
        "first": {"unique": elf + b"first", "shared": elf, "changed": elf + b"before"},
        "second": {"unique": elf + b"second", "shared": elf, "changed": elf + b"other"},
    }
    for module, libraries in dependencies.items():
        with ZipFile(output / f"{module}.aar", "w") as archive:
            archive.writestr("AndroidManifest.xml", '<manifest package="example.sdk"/>')
            for name, payload in libraries.items():
                archive.writestr(f"jni/arm64-v8a/lib{name}.so", payload)

    with ZipFile(output / "app.apk", "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", "synthetic fixture manifest")
        libraries = {**dependencies["first"], "changed": elf + b"after"}
        for name, payload in libraries.items():
            archive.writestr(f"lib/arm64-v8a/lib{name}.so", payload)

    manifest = {
        "consumer_configuration": ":app:demoDebugRuntimeClasspath",
        "artifacts": [
            {"coordinate": f"example:{module}:1.0", "path": f"{module}.aar"}
            for module in dependencies
        ],
    }
    (output / "resolved-aars.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    generate(parser.parse_args().output)
