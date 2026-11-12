---
name: android-jni-doctor
description: Diagnose Android UnsatisfiedLinkError using a final APK, the target device ABI, and a log from the failed run. Check missing native libraries, ELF architecture mismatches, and logged JNI binding failures.
license: MIT
---

# Android JNI Doctor

Use the APK delivered to the target device, the ABI selected for the app
process, and an `UnsatisfiedLinkError` excerpt from the same run.

```sh
python scripts/jni_doctor.py app.apk --abi arm64-v8a --log app-log.txt
```

Supply `--library libdevice.so` if the failure lacks a filename and you know
which library to inspect. Report the JSON kind and its evidence. An absent
entry refers to the supplied APK only. A binding failure refers to the log
and may require source or runtime checks for `RegisterNatives`.
