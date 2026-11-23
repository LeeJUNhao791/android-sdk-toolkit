# Contributing

Issues and pull requests are welcome in English or Chinese. Include the
revision, Python version, exact command, expected result, and actual JSON or
error output. Use a small reproducible sample and remove credentials and
private SDK files from shared reports.

Keep each pull request focused. Add a regression case for changed behavior
and update both README files when the documented inputs or results change.

## Local checks

Run the CLI and Action test suites from the repository root with Python 3.11:

```sh
python -B -m unittest discover -s skills/aar-delivery-check/tests -v
python -B -m unittest discover -s skills/android-jni-doctor/tests -v
python -B -m unittest discover -s skills/android-sdk-pack/tests -v
python -B -m unittest discover -s skills/apk-page-size-check/tests -v
```

For Gradle handoff changes, install the JDK and Android tools listed in the
[README](README.md#package-and-verify-an-sdk-handoff), then run:

```sh
python -B -m unittest discover -s tests -v
```

[SDK Toolkit CI](.github/workflows/ci.yml) defines the Windows/Linux checks
and Android integration tools. State which checks you ran. Generated APK
fixtures verify the checker; real-build provenance and device runtime results
need their own evidence.
