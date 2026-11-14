---
name: apk-page-size-check
description: Preflight 16 KB native library alignment in a final Android APK. Check 64-bit ELF LOAD segments and uncompressed native ZIP data offsets before a separate 16 KB runtime test.
license: MIT
---

# APK page size check

Run with Python 3.8 or newer on the final APK distributed to users.

```sh
python scripts/check_apk.py app.apk
```

The JSON report lists each `lib/<abi>/*.so` entry and its ELF and ZIP results.
Report the entry path, any failing LOAD program headers, and any misaligned
ZIP data offset. An ELF result of `not_applicable` means the entry is 32-bit.
A ZIP result of `compressed` means ZIP data offset alignment is inapplicable.

Exit codes are 0 for passing alignment checks, 1 for misalignment, 2 for
invalid or unsupported input, and 3 when there are no ARM64 or x86-64 libraries
and the applicable ZIP checks found no issue.

Use `--aar-manifest resolved-aars.json` when you have the external AAR paths
and resolved coordinates from the consumer variant's Gradle runtime classpath.
Supply a JSON object with `consumer_configuration` (for example
`:app:demoDebugRuntimeClasspath`) and an `artifacts` array of objects with
`coordinate` (`group:module:version`) and `path` (an absolute or manifest-relative
`.aar` path). For alignment failures, `origin` compares the ABI, filename and
SHA-256 of the native payload. Treat matches as candidates among the supplied
AARs. APK-only analysis or a native binary changed during packaging can leave
its origin undetermined.

Run on each APK delivered to the device when using split APKs. This check covers
native alignment in the supplied APK. Assess GNU_RELRO layout separately and
verify installation and JNI execution on a device or emulator where
`adb shell getconf PAGE_SIZE` returns `16384`.
See [Android's 16 KB page size guide](https://developer.android.com/guide/practices/page-sizes).
