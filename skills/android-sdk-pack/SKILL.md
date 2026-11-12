---
name: android-sdk-pack
description: Package a Gradle Android AAR or Java JAR for SDK handoff and validate a separate consumer against a fresh local Maven repository. Use for release artifacts, Maven coordinates, and transitive dependency smoke tests.
license: MIT
---

# SDK Packaging and Consumer Check

Confirm the Maven coordinate and whether the producer publishes an Android AAR
or a Java JAR. Use a separate consumer that depends on the artifact by
coordinate and exercises a public API.

Configure a Gradle Maven repository named `handoff` using the `toolkitRepo`
property. In the consumer, resolve the `toolkitCoordinate` dependency from
that repository. Use `assembleDebug` as the AAR consumer check and `run` as
the JAR consumer check. For multiple matching tasks or Android flavors, pass
`--consumer-task` with a full task path such as `:app:assembleDemoDebug` or
`:cli:run`. The check uses the selected task's project and runtime classpath.

```sh
python scripts/publish_sdk.py producer consumer --kind aar --coordinate example:sdk:1.0 --output build/handoff
```

Set `JAVA_HOME` to the JDK used for the Gradle build. Use `--wrapper` if the
producer shares a Gradle wrapper from another project. Report the artifact,
POM and consumer task after success. The script also checks that a consumer
runtime classpath resolves the expected Maven coordinate and matches the
published artifact's SHA-256. Treat an Android compile as evidence of
dependency resolution and compilation. Run a device test for JNI behavior.
