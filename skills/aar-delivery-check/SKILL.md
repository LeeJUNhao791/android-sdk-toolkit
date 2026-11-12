---
name: aar-delivery-check
description: Check an Android AAR against expected native libraries, target ABIs, and required archive entries such as R8 consumer rules. Verify ELF headers when reviewing native SDK handoffs, releases, or a suspected ABI mismatch.
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
JSON status and any missing paths. Add `--verify-abi` to check the ELF
architecture of the present native libraries listed in `native_libraries`.
Report both the expected and detected ABI on a mismatch.

Exit 0 means the selected checks passed, 1 means a delivery check failed,
and 2 means input or usage error. Treat APK packaging, JNI loading, and
R8 behavior as separate checks that require the corresponding build or runtime
evidence.
