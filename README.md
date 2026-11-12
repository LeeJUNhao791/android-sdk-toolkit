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

## Package and verify an SDK handoff

Publish a Gradle AAR or JAR into a fresh local Maven repository, then check
that a separate consumer can use the published coordinate. Set `JAVA_HOME`
to a JDK 17 installation for the examples and run from the repository root.

```sh
python skills/android-sdk-pack/scripts/publish_sdk.py examples/android-sdk examples/consumers/android --kind aar --coordinate io.github.leejunhao791.sdktoolkit:device-sdk:0.1.0 --output build/handoff-aar
python skills/android-sdk-pack/scripts/publish_sdk.py examples/java-sdk examples/consumers/java --wrapper examples/android-sdk --kind jar --coordinate io.github.leejunhao791.sdktoolkit:java-device-sdk:0.1.0 --output build/handoff-jar
```

Choose a fresh output directory for each run. The script delivers the Maven
repository after the consumer check succeeds. The JSON includes the artifact
and POM paths. The Android consumer assembles an APK that compiles a call
to the SDK. The Java consumer runs a call that uses a transitive dependency
declared by the JAR producer.

For your own SDK, use a Gradle Maven repository named `handoff` that reads
`toolkitRepo` as its URL. The consumer resolves `toolkitCoordinate` from
`toolkitRepo`, then exposes `assembleDebug` for AARs or `run` for JARs. The
[SDK packaging Skill](skills/android-sdk-pack) and the example projects show
the required setup. The script invokes Gradle builds from the supplied projects.

Run the handoff tests with
`python -B -m unittest discover -s skills/android-sdk-pack/tests -v`.

## License

[MIT](LICENSE)
