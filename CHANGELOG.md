# Changelog

## Unreleased

- Extend the same-build native provenance Gradle exporter to select an Android application module and exact Debug/Release or product-flavor variant. Keep the default `:app` Debug command and JSON schemas compatible; isolate other variants' reports and reject multiple APK outputs.

## [0.10.0] - 2026-11-26

- Add `check_apk.py --output-dir` to save scanner JSON and an English/Simplified Chinese Markdown draft together in a new directory. Successful evidence writes preserve JSON on stdout and scanner exit codes `0`/`1`/`2`/`3`. Existing output paths are refused without overwriting them; evidence generation errors return `2`. [#14](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/14)
- Update both READMEs with bilingual report commands and current published Action usage. [#13](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/13)

- Show an actual MediaPipe scan and generated report on both homepages, with input hashes and reproduction instructions.

These are static APK alignment reports. They do not establish Google Play acceptance or Android device runtime behavior.

## [0.9.0] - 2026-11-25

- Add bilingual Markdown drafts from APK checker JSON, including available AAR candidates and SHA-256 evidence. [#12](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/12)
- Document ELF and ZIP alignment troubleshooting in English and Simplified Chinese. [#11](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/11)
- Verify the published Action and add project entry points and contribution guidance. [#10](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/10)

See [GitHub Releases](https://github.com/LeeJUNhao791/android-sdk-toolkit/releases) for earlier versions.

[0.10.0]: https://github.com/LeeJUNhao791/android-sdk-toolkit/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/LeeJUNhao791/android-sdk-toolkit/releases/tag/v0.9.0
