# Android SDK Toolkit

Small command-line tools and Agent Skills for delivering and integrating Android SDKs.

## AAR delivery check

Find missing files before handing an AAR to another team. For example, an AAR
with `jni/arm64-v8a/libdevice.so` and no `jni/x86_64/libdevice.so` fails a contract
that requires both ABIs.

Run the check with Python 3.8 or newer. It uses only the standard library.

```sh
python skills/aar-delivery-check/scripts/check_aar.py vendor.aar --expect skills/aar-delivery-check/examples/expect.json
```

Use `native_libraries` to map library filenames to required ABIs. Use
`required_entries` for exact archive paths, such as `proguard.txt` if the
delivery calls for that file. The script always requires `AndroidManifest.xml`.
The JSON report lists the checked paths and missing entries. Exit 0 means
pass, 1 means missing entries, and 2 means invalid input.

The AAR check verifies file presence. Check the final APK and run the app
to verify native loading.

### Try three fixtures

Run these commands separately. The last two checks return exit code 1.

```sh
python skills/aar-delivery-check/examples/generate.py build/aar-fixtures
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/complete.aar --expect skills/aar-delivery-check/examples/expect.json
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/missing-x86_64.aar --expect skills/aar-delivery-check/examples/expect.json
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/missing-r8-rules.aar --expect skills/aar-delivery-check/examples/expect.json
```

The fixtures exercise ZIP entry checks. The native entries in these fixtures
are placeholders.

### Build the Android example

The [example SDK](examples/android-sdk) uses JDK 17, Android SDK Platform 35,
NDK `28.2.13676358`, and CMake `3.22.1`. Run from its directory:

```sh
./gradlew :sdk:assembleRelease
```

On Windows, use `gradlew.bat`. From the repository root, check the real AAR:

```sh
python skills/aar-delivery-check/scripts/check_aar.py examples/android-sdk/sdk/build/outputs/aar/sdk-release.aar --expect skills/aar-delivery-check/examples/expect.json
python -B -m unittest discover -s skills/aar-delivery-check/tests -v
```

Copy [`skills/aar-delivery-check`](skills/aar-delivery-check) to your Agent Skills
directory to use it as a Skill. See the
[Android AAR documentation](https://developer.android.com/studio/projects/android-library#aar-contents)
for the archive layout.

## License

[MIT](LICENSE)
