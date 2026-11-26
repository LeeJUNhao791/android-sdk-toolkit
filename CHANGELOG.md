# Changelog

## [Unreleased] (planned v0.10.0)

- Add `check_apk.py --output-dir` to save scanner JSON and an English/Simplified Chinese Markdown draft together in a new directory. Successful evidence writes preserve JSON on stdout and scanner exit codes `0`/`1`/`2`/`3`. Existing output paths are refused without overwriting them; evidence generation errors return `2`. [#14](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/14)
- Update both READMEs with bilingual report commands and current published Action usage. [#13](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/13)

These are static APK alignment reports. They do not establish Google Play acceptance or Android device runtime behavior.

## [0.9.0] - 2026-11-25

- Add bilingual Markdown drafts from APK checker JSON, including available AAR candidates and SHA-256 evidence. [#12](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/12)
- Document ELF and ZIP alignment troubleshooting in English and Simplified Chinese. [#11](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/11)
- Verify the published Action and add project entry points and contribution guidance. [#10](https://github.com/LeeJUNhao791/android-sdk-toolkit/pull/10)

See [GitHub Releases](https://github.com/LeeJUNhao791/android-sdk-toolkit/releases) for earlier versions.

[Unreleased]: https://github.com/LeeJUNhao791/android-sdk-toolkit/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/LeeJUNhao791/android-sdk-toolkit/releases/tag/v0.9.0
