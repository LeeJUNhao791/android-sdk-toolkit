---
name: aar-delivery-check
description: Check an Android AAR against expected native libraries, target ABIs, and required archive entries such as R8 consumer rules. Use for SDK handoffs, release checks, and missing files in delivered AARs.
license: MIT
---

# AAR Delivery Check

Obtain the expected library names and ABIs from the SDK's delivery requirements.
Use [examples/expect.json](examples/expect.json) as a model. Add a consumer
rules entry only when the delivery requires a specific archive path.

```sh
python scripts/check_aar.py vendor.aar --expect expect.json
```

Use the script's absolute path when running from another directory. Report the
JSON status and any missing paths. Exit 0 means the delivery requirements
passed, 1 means expected entries are missing, and 2 means input or usage error.

The script inspects archive entries. Treat APK packaging, JNI loading, and
R8 behavior as separate checks that require the corresponding build or runtime
evidence.
