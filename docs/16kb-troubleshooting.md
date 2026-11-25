# Troubleshoot APK 16 KB alignment

[简体中文](16kb-troubleshooting.zh-CN.md)

Run these commands from the Toolkit checkout. Use the signed APK you plan to
distribute in place of `app-release.apk`. For split delivery, check each
distributed APK.

```sh
python skills/apk-page-size-check/scripts/check_apk.py app-release.apk
```

## Fix the failing check

- **`elf: fail`** means a `PT_LOAD` segment in the `.so` fails the alignment
  check. Rebuild the library with 16 KB ELF alignment. NDK r28 and later enable
  it by default. For a prebuilt SDK, upgrade to a version with a compatible
  library or request a rebuilt AAR. Rebuild the app and check the final APK.
  [Android build instructions](https://developer.android.com/guide/practices/page-sizes#compile-16-kb-alignment)
- **`zip: fail`** means an uncompressed `.so` starts at the wrong offset in
  the APK. For Gradle builds with uncompressed libraries, use Android Gradle
  Plugin 8.5.1 or later. For custom packaging with `apksigner`, align the
  unsigned APK with `zipalign -P 16 -v 4 unsigned.apk aligned.apk`, then sign
  `aligned.apk`. Check the final signed APK with the Toolkit command above and
  the Android Build Tools commands below. Use the full paths to the tools or
  add the Build Tools directory to your `PATH`.
  [Android packaging instructions](https://developer.android.com/guide/practices/page-sizes#update-packaging) · [zipalign](https://developer.android.com/tools/zipalign)

```sh
zipalign -c -P 16 -v 4 app-release.apk
apksigner verify app-release.apk
```

## Trace a failing library to an AAR version

Export the AARs resolved for the APK's Gradle variant, including transitive
dependencies. Pass the manifest with `--aar-manifest` and look for the failing
library under `libraries`. A `single_candidate` in `origin.status` means one
supplied AAR has a byte-for-byte match. Read its version in
`origin.candidates[].coordinate` and confirm it against the same variant's
resolved dependencies. If Gradle changed the library when stripping symbols,
use provenance from the same build.
[Export the resolved AARs](../README.md#find-candidate-aars-for-failing-native-libraries) · [Trace stripped libraries](../README.md#trace-a-stripped-library-from-the-same-gradle-build)

The public WebRTC AAR `io.github.webrtc-sdk:android:104.5112.10` supplies
`jni/arm64-v8a/libjingle_peerconnection_so.so`. In a signed ARM64 inspection
APK, its three `PT_LOAD` segments have `p_align=4096`, so the checker reports
`elf: fail`, `zip: pass`, and `single_candidate` for that version. In an
equivalently packaged APK with version `150.7871.01`, all three segments have
`p_align=16384` and both checks pass. The manifest explicitly supplies the
candidate AAR, and both samples have 16 KB ZIP alignment. This verifies the
ARM64 ELF and ZIP layout. Use your app build and runtime tests to evaluate an
SDK upgrade.
[WebRTC 104.5112.10](https://repo.maven.apache.org/maven2/io/github/webrtc-sdk/android/104.5112.10/) · [WebRTC 150.7871.01](https://repo.maven.apache.org/maven2/io/github/webrtc-sdk/android/150.7871.01/)

## Draft a report for a supplier

Save the checker JSON and run the local report command with Python 3.8+.

```sh
python skills/apk-page-size-check/scripts/check_apk.py app.apk --aar-manifest resolved-aars.json > apk-16kb.json
python skills/apk-page-size-check/scripts/render_vendor_report.py apk-16kb.json -o vendor-report.md
```

The checker saves JSON even when alignment fails (exit code `1`). The report
command exits `0` after writing a draft and `2` if the JSON has unusable
alignment results or the output cannot be written. Omit `-o` to write UTF-8
Markdown to standard output. With `-o`, choose a new file.

Review the draft before sharing. A single byte match covers the AARs in the
supplied manifest. For a verified same-build strip chain, check ELF alignment
on the matched AAR member itself before contacting the supplier. Collect more
provenance when multiple or no candidates match. Route ZIP alignment failures
to app packaging. The draft includes SO digests where available. Compute the
full AAR digest separately if a supplier requests it.

## Reproduce the WebRTC comparison

Use Python 3.8+, JDK 17 (`JAVA_HOME`), Android SDK Platform 35 and Build Tools
36.0.0 (`ANDROID_HOME`). Save the snippet as `build/reproduce_webrtc.py`,
creating `build/` if needed. Run it from the checkout root with
`python build/reproduce_webrtc.py`. It downloads the two versioned AARs into a
fresh `build/webrtc-16kb/` directory and signs minimal inspection APKs using a
temporary local key.

```python
import json
import os
from pathlib import Path
from shutil import copyfile
from subprocess import check_call
from tempfile import TemporaryDirectory
from urllib.request import urlretrieve
from zipfile import ZipFile

sdk = Path(os.environ["ANDROID_HOME"])
tools = sdk / "build-tools" / "36.0.0"
jdk_bin = Path(os.environ["JAVA_HOME"]) / "bin"
exe = ".exe" if os.name == "nt" else ""
aapt2 = tools / f"aapt2{exe}"
zipalign = tools / f"zipalign{exe}"
signer = [jdk_bin / f"java{exe}", "-jar", tools / "lib" / "apksigner.jar"]
out = Path("build/webrtc-16kb")
out.mkdir(parents=True)
manifest = out / "AndroidManifest.xml"
manifest.write_text(
    '<manifest xmlns:android="http://schemas.android.com/apk/res/android" '
    'package="example.webrtccheck"><application android:hasCode="false" '
    'android:extractNativeLibs="false"/></manifest>', encoding="utf-8"
)
base = out / "base.apk"
check_call([aapt2, "link", "-I", sdk / "platforms/android-35/android.jar",
            "--manifest", manifest, "--min-sdk-version", "23", "-o", base])
library = "arm64-v8a/libjingle_peerconnection_so.so"
with TemporaryDirectory() as scratch:
    key = Path(scratch) / "fixture.p12"
    check_call([jdk_bin / f"keytool{exe}", "-genkeypair", "-keystore", key,
                "-storepass", "fixture", "-alias", "fixture", "-keyalg", "RSA",
                "-dname", "CN=16 KB inspection fixture"])
    for version in ("104.5112.10", "150.7871.01"):
        aar = out / f"android-{version}.aar"
        maven = "https://repo.maven.apache.org/maven2/io/github/webrtc-sdk/android"
        urlretrieve(f"{maven}/{version}/{aar.name}", aar)
        unsigned = out / f"{version}-unsigned.apk"
        aligned = out / f"{version}-aligned.apk"
        apk = out / f"{version}.apk"
        copyfile(base, unsigned)
        with ZipFile(aar) as dependency, ZipFile(unsigned, "a") as archive:
            archive.writestr(f"lib/{library}", dependency.read(f"jni/{library}"))
        check_call([zipalign, "-P", "16", "4", unsigned, aligned])
        check_call([*signer, "sign", "--ks", key, "--ks-pass", "pass:fixture",
                    "--out", apk, aligned])
        check_call([*signer, "verify", apk])
        check_call([zipalign, "-c", "-P", "16", "4", apk])
        (out / f"{version}-aars.json").write_text(json.dumps({
            "consumer_configuration": "manual-fixture:arm64-v8a",
            "artifacts": [{"coordinate": f"io.github.webrtc-sdk:android:{version}",
                           "path": aar.name}],
        }), encoding="utf-8")
```

Run the checks separately. The first command is expected to return exit 1
with the older version as the only candidate. The second returns exit 0 with
`elf: pass` and `zip: pass`.

```sh
python skills/apk-page-size-check/scripts/check_apk.py build/webrtc-16kb/104.5112.10.apk --aar-manifest build/webrtc-16kb/104.5112.10-aars.json
python skills/apk-page-size-check/scripts/check_apk.py build/webrtc-16kb/150.7871.01.apk --aar-manifest build/webrtc-16kb/150.7871.01-aars.json
```
