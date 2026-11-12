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
pass, 1 means a delivery check failed, and 2 means invalid input.

### Try the missing-entry fixtures

Run these commands separately. The last two checks return exit code 1.

```sh
python skills/aar-delivery-check/examples/generate.py build/aar-fixtures
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/complete.aar --expect skills/aar-delivery-check/examples/expect.json
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/missing-x86_64.aar --expect skills/aar-delivery-check/examples/expect.json
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/missing-r8-rules.aar --expect skills/aar-delivery-check/examples/expect.json
```

The fixtures use small test ELF headers. Build the Android example below
to check complete NDK-built libraries.

### Verify native architecture

Add `--verify-abi` to compare the ELF class and machine with each present
entry listed in `native_libraries`. Android uses little-endian ELF. Missing
entries stay in `missing_entries`. Header results appear in `abi_checks`,
including the expected and detected ABI when available.

```sh
python skills/aar-delivery-check/scripts/check_aar.py build/aar-fixtures/wrong-abi.aar --expect skills/aar-delivery-check/examples/expect.json --verify-abi
```

This fixture has every expected path. The library under
`jni/arm64-v8a/libdevice.so` contains an x86-64 header, so ABI verification
reports `abi_mismatch` and returns exit code 1. Check the final APK and run
the app to verify native loading. See the
[Android ABI guide](https://developer.android.com/ndk/guides/abis).

### Build the Android example

The [example SDK](examples/android-sdk) uses JDK 17, Android SDK Platform 35,
NDK `28.2.13676358`, and CMake `3.22.1`. Run from its directory:

```sh
./gradlew :sdk:assembleRelease
```

On Windows, use `gradlew.bat`. From the repository root, check the real AAR:

```sh
python skills/aar-delivery-check/scripts/check_aar.py examples/android-sdk/sdk/build/outputs/aar/sdk-release.aar --expect skills/aar-delivery-check/examples/expect.json --verify-abi
python -B -m unittest discover -s skills/aar-delivery-check/tests -v
```

Copy [`skills/aar-delivery-check`](skills/aar-delivery-check) to your Agent Skills
directory to use it as a Skill. See the
[Android AAR documentation](https://developer.android.com/studio/projects/android-library#aar-contents)
for the archive layout.

## JNI load diagnosis

Give the checker the final APK, the app's selected ABI, and a log from the
same failed run.

```sh
python skills/android-jni-doctor/scripts/jni_doctor.py app.apk --abi arm64-v8a --log app-log.txt
```

Use `--library libdevice.so` when you know the library and the log omits its
filename. The JSON report identifies a missing APK entry, an ELF architecture
mismatch, or a logged JNI binding failure when the evidence supports it.
Exit 0 means the report was produced, including an undetermined result.
Exit 2 means invalid input.

The package check covers the supplied APK. Installed split APKs, system
libraries, and runtime `RegisterNatives` behavior may need separate evidence.
See the [Android JNI guide](https://developer.android.com/ndk/guides/jni-tips).

Build `:app:assembleDebug` in [the Android example](examples/android-sdk)
and install its debug APK on a test device or emulator. Launch it with
`adb shell am start -S -n io.github.leejunhao791.sdktoolkit.demo/.MainActivity`
to run the successful native call. Add `--es scenario missing` for a
missing-library error or `--es scenario binding` for a method-binding error.
The `SdkToolkitDemo` log tag records the result. Capture that log in UTF-8
for the checker.

Run the diagnosis tests with
`python -B -m unittest discover -s skills/android-jni-doctor/tests -v`.

## Check 16 KB alignment in a final APK

```sh
python skills/apk-page-size-check/scripts/check_apk.py app.apk
```

The checker uses Python 3.8 or newer and the standard library. It inspects
`lib/<abi>/*.so` entries in the supplied APK:

- For ARM64 and x86-64 libraries, every ELF `PT_LOAD` segment must declare a
  power-of-two alignment of at least 16 KB. Its file offset and virtual
  address must be congruent modulo that alignment.
- For uncompressed libraries in the four supported Android ABIs, the ZIP
  entry's data must start at a 16 KB boundary. Compressed 64-bit libraries
  still get the ELF check.

The JSON report lists the affected paths, LOAD program headers and ZIP data
offsets. Exit 0 means the scoped alignment checks passed, 1 means an alignment
failure, 2 means invalid or unsupported input, and 3 means there were no
64-bit libraries and no ZIP alignment failures. A single APK report covers
that file. For a split delivery, check each distributed APK.

A pass is static alignment evidence. GNU_RELRO layout and APK installation and
JNI execution on a 16 KB Android system require separate checks. See
[Android's 16 KB page size guide](https://developer.android.com/guide/practices/page-sizes)
and the [runtime procedure below](#verify-the-aar-on-an-android-device).

## Package and verify an SDK handoff

Publish a Gradle AAR or JAR into a fresh local Maven repository, then check
that a separate consumer can use the published coordinate. Set `JAVA_HOME`
to a JDK 17 installation for the examples and run from the repository root.

```sh
python skills/android-sdk-pack/scripts/publish_sdk.py examples/android-sdk examples/consumers/android --kind aar --coordinate io.github.leejunhao791.sdktoolkit:device-sdk:0.1.0 --output build/handoff-aar
python skills/android-sdk-pack/scripts/publish_sdk.py examples/java-sdk examples/consumers/java --wrapper examples/android-sdk --kind jar --coordinate io.github.leejunhao791.sdktoolkit:java-device-sdk:0.1.0 --output build/handoff-jar
```

Choose a fresh output directory for each run. The script delivers the Maven
repository after it verifies the selected artifact on a consumer runtime
classpath and the smoke task succeeds. It matches the resolved Maven
coordinate and compares SHA-256 with the freshly published AAR or JAR.
The JSON includes the artifact and POM paths and `consumer_artifact_verified`.
The Android consumer assembles an APK that compiles a call to the SDK. The Java
consumer runs a call that uses a transitive dependency declared by the JAR
producer.

For your own SDK, use a Gradle Maven repository named `handoff` that reads
`toolkitRepo` as its URL. The consumer resolves `toolkitCoordinate` from
`toolkitRepo`, then exposes `assembleDebug` for AARs or `run` for JARs. The
[SDK packaging Skill](skills/android-sdk-pack) and the example projects show
the required setup. The script invokes Gradle builds from the supplied projects.

For multiple matching tasks or Android flavors, pass a full Gradle task path
with `--consumer-task`, such as `:app:assembleDemoDebug` for an AAR or
`:cli:run` for a JAR. The artifact check uses that task's project and runtime
classpath, such as `demoDebugRuntimeClasspath` for `assembleDemoDebug`.

Run the handoff tests with
`python -B -m unittest discover -s skills/android-sdk-pack/tests -v`.

### Verify the AAR on an Android device

Use a phone, development board, or emulator running 64-bit Android 6.0 (API 23)
or later. Enable ADB and check that the system exposes `arm64-v8a` or `x86_64`.
For ARM64 acceptance, use `arm64-v8a`. Run from the repository root with the
Android build tools listed above. Use a fresh
`build/device-handoff` directory. On Windows, use `gradlew.bat` in place of
`gradlew`.

```sh
python skills/android-sdk-pack/scripts/publish_sdk.py examples/android-sdk examples/consumers/android --kind aar --coordinate io.github.leejunhao791.sdktoolkit:device-sdk:0.1.0 --output build/device-handoff
./examples/android-sdk/gradlew -p examples/consumers/android "-PtoolkitRepo=$PWD/build/device-handoff" "-PtoolkitCoordinate=io.github.leejunhao791.sdktoolkit:device-sdk:0.1.0" :assembleDebug :assembleDebugAndroidTest
adb install -r examples/consumers/android/build/outputs/apk/debug/aar-consumer-debug.apk
adb install -r -t examples/consumers/android/build/outputs/apk/androidTest/debug/aar-consumer-debug-androidTest.apk
adb shell am instrument -w -r io.github.leejunhao791.sdktoolkit.consumer.test/io.github.leejunhao791.sdktoolkit.consumer.JniSmokeRunner
```

If multiple devices are connected, pass `-s SERIAL` to each ADB command.
The test calls `DeviceSdk.roundTrip(42)` through the consumer app. A pass
includes `jni_result=42` and `INSTRUMENTATION_CODE: -1`. For ARM64, check
`process_64_bit=true` and confirm that the following command shows
`primaryCpuAbi=arm64-v8a`:

```sh
adb shell dumpsys package io.github.leejunhao791.sdktoolkit.consumer
```

Measure the device's page size with `adb shell getconf PAGE_SIZE` before
running the test. A 16 KB environment reports `16384`.

| Device | Android | App ABI | Page size | JNI result |
| --- | --- | --- | --- | --- |
| Pixel 4 XL | 11 (API 30, `RQ2A.210505.002`) | `arm64-v8a` | Unrecorded | Pass, returned `42` in a 64-bit process |
| Qualcomm Kalama | 15 (API 35, `AQ3A.250716.002`) | `arm64-v8a` | 4 KB (`4096`) | Pass, returned `42` in a 64-bit process |
| OnePlus PJA110 | 16 (API 36, `BP2A.250605.015`) | `arm64-v8a` | 4 KB (`4096`) | Pass, returned `42` in a 64-bit process |
| Qualcomm Volcano | 16 (API 36, `BQ2A.250622.001-BP2A.250605.031.A3`) | `arm64-v8a` | 4 KB (`4096`) | Pass, returned `42` in a 64-bit process |

Runtime checks on an ARM64 device with 16 KB pages and on Android 6.0
(API 23) are pending.

## Regression checks

[SDK Toolkit CI](https://github.com/LeeJUNhao791/android-sdk-toolkit/actions/workflows/ci.yml) runs the Skill tests on
Windows and Linux. The Linux integration job builds the JNI test APK and
checks the real AAR and JAR examples. It rejects an x86-64 library in the ARM64
AAR path and verifies that the selected consumer module and variant resolve
the published SDK bytes at the requested coordinate. It runs the 16 KB
alignment preflight and Android Build Tools' `zipalign` on the real Android
consumer APK. The Python tests also use generated APKs to isolate ELF and ZIP
alignment failures.

With JDK 17 and the Android tools listed above, run the integration tests
locally from the repository root:

```sh
python -B -m unittest discover -s tests -v
```

## License

[MIT](LICENSE)
