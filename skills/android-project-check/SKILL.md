---
name: android-project-check
description: Inspect local AARs in an Android or uni-app UTS project directory without running Gradle. Inventory relative paths, SHA-256, manifest presence, ABI headers and 64-bit ELF LOAD alignment; optionally save JSON and a bilingual supplier draft.
license: MIT
---

# Android Project Check

Use this bounded local pilot when AARs are already present in a project. It
checks direct files in `app/libs/*.aar` and
`uni_modules/*/utssdk/app-android/libs/*.aar` only (`.aar` suffix is case
insensitive). It does not discover Gradle dependencies, caches, other modules
or Prefab libraries. Native entry scope is `jni/<abi>/*.so`.

```sh
python scripts/check_project.py "/path/to/project"
python scripts/check_project.py "/path/to/project" --expect-abi arm64-v8a --output-dir "/path/to/new-evidence"
```

Use the script's absolute path outside this Skill directory. Keep the sibling
`aar-delivery-check` and `apk-page-size-check` Skills available: this command
reuses their ABI/ELF parsing functions. Python 3.8+ and its standard library
are sufficient; no Android SDK or network access is needed.

`--expect-abi` is repeatable and optional. Each requested ABI is required in
**every discovered AAR**, including Java-only AARs; Java-only AARs fail an
explicit ABI requirement. Without this flag no ABI is required, including
`x86_64`. Directory ABI labels are compared with detected ELF architecture.
ELF alignment is evaluated only for little-endian ARM64/x86-64 shared objects.
32-bit libraries receive a header ABI check only, with alignment
`not_applicable`. `elf64_count: 0` means no 64-bit ELF alignment was evaluated;
an overall pass does not imply a 64-bit library exists.

JSON uses its own project/AAR schema and sorted relative POSIX source paths.
It includes AAR and native-member SHA-256, manifest presence, discovered/missing
ABIs, ABI header status, ELF alignment and failing `PT_LOAD` values. Manifest
checking means presence/readability, not XML semantics or Android compatibility.
All file members are streamed to check archive CRC; nothing is extracted.
Duplicate or unsafe ZIP names, invalid archives, absent manifests and invalid
or unsupported native ELF inputs are invalid. Preserve other AAR results when
one AAR is invalid.

| Exit | Status | Meaning |
| --- | --- | --- |
| 0 | `pass` | Discovered AARs passed the selected static checks |
| 1 | `fail` | Missing explicit ABI, ABI mismatch or ELF alignment failure |
| 2 | `invalid` | Invalid/unreadable input, unsupported native input, path or output error |
| 3 | `no_matches` | No matching AARs; this is not a pass |

Invalid input takes precedence over failures; failures take precedence over
passes. Output errors also return `2`; check stderr as well as JSON status.
Argument/output preflight errors have no scanner JSON. Existing output paths
are refused before scanning. A fresh `--output-dir` must resolve outside the
project and receives UTF-8 `report.json` and bilingual `report.md`; stdout
remains JSON. Do not overwrite an earlier evidence directory.

The supplied project root resolves once. Symlinks/junctions/reparse points
under it on inspected paths are invalid and are not followed. Project inputs
are read-only. Do not run builds, edit projects, repair binaries, infer vendor
versions or generate patches as part of this check.

Report exact artifact paths/hashes and static findings. AAR ZIP layout is not
APK ZIP alignment. Final APK packaging, installation, JNI execution and
behavior on a 16 KB device require separate evidence. Review supplier drafts
before sharing.

Run `python -B -m unittest discover -s skills/android-project-check/tests -v`
from the Toolkit repository root.
