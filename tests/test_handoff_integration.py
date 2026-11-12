import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
AAR_CHECK = ROOT / "skills/aar-delivery-check/scripts/check_aar.py"
CONTRACT = ROOT / "skills/aar-delivery-check/examples/expect.json"
PUBLISH = ROOT / "skills/android-sdk-pack/scripts/publish_sdk.py"
GROUP = "io.github.leejunhao791.sdktoolkit"
JAR_COORDINATE = f"{GROUP}:java-device-sdk:0.1.0"


class HandoffIntegration(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="sdk-toolkit-regression-")
        self.addCleanup(directory.cleanup)
        self.output = Path(directory.name)

    def run_tool(self, script, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(script), *map(str, args)],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=360,
        )
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        return result

    def test_real_aar_rejects_x86_library_in_arm64_directory(self):
        handoff = self.run_tool(
            PUBLISH, "examples/android-sdk", "examples/consumers/android",
            "--kind", "aar", "--coordinate", f"{GROUP}:device-sdk:0.1.0",
            "--output", self.output / "aar-handoff",
        )
        report = json.loads(handoff.stdout)
        self.assertTrue(report["consumer_artifact_verified"])
        original = Path(report["artifact"])
        accepted = self.run_tool(AAR_CHECK, original, "--expect", CONTRACT, "--verify-abi")
        self.assertEqual(json.loads(accepted.stdout)["status"], "pass")

        altered = self.output / "wrong-abi.aar"
        arm = "jni/arm64-v8a/libdevice.so"
        x86 = "jni/x86_64/libdevice.so"
        with ZipFile(original) as source, ZipFile(altered, "w") as target:
            for name in source.namelist():
                target.writestr(name, source.read(x86 if name == arm else name))
        rejected = self.run_tool(
            AAR_CHECK, altered, "--expect", CONTRACT, "--verify-abi", expected=1,
        )
        report = json.loads(rejected.stdout)
        self.assertEqual(report["missing_entries"], [])
        check = next(item for item in report["abi_checks"] if item["entry"] == arm)
        self.assertEqual((check["status"], check["detected_abi"]), ("abi_mismatch", "x86_64"))

    def test_jar_consumer_must_resolve_the_published_artifact(self):
        args = ("--wrapper", "examples/android-sdk", "--kind", "jar",
                "--coordinate", JAR_COORDINATE)
        verified = self.output / "jar-handoff"
        success = self.run_tool(
            PUBLISH, "examples/java-sdk", "examples/consumers/java", *args, "--output", verified,
        )
        report = json.loads(success.stdout)
        self.assertTrue(report["consumer_artifact_verified"])
        self.assertIn("Java SDK and transitive dependency returned 42", success.stderr)

        original = Path(report["artifact"])
        shadow = self.output / "shadow-repo"
        changed = shadow / original.relative_to(verified)
        changed.parent.mkdir(parents=True)
        shutil.copyfile(original, changed)
        with ZipFile(changed, "a") as jar:
            jar.writestr("regression-fixture.txt", "Different artifact at the same coordinate.")
        changed.with_suffix(".pom").write_text(
            "<project><modelVersion>4.0.0</modelVersion>"
            f"<groupId>{GROUP}</groupId><artifactId>java-device-sdk</artifactId>"
            "<version>0.1.0</version></project>",
            encoding="utf-8",
        )

        for case in ("unused", "wrong-bytes"):
            with self.subTest(case=case):
                consumer = self.output / case
                consumer.mkdir()
                (consumer / "settings.gradle").write_text(
                    f"rootProject.name = '{case}'\n", encoding="utf-8",
                )
                build = "tasks.register('run') { doLast { println 'Smoke task succeeds' } }\n"
                if case == "wrong-bytes":
                    build = (
                        "plugins { id 'java' }\n"
                        f"repositories {{ maven {{ url = uri('{shadow.as_uri()}') }} }}\n"
                        f"dependencies {{ implementation '{JAR_COORDINATE}' }}\n" + build
                    )
                (consumer / "build.gradle").write_text(build, encoding="utf-8")
                output = self.output / f"{case}-handoff"
                rejected = self.run_tool(
                    PUBLISH, "examples/java-sdk", consumer, *args, "--output", output, expected=2,
                )
                self.assertIn("Consumer did not resolve the matching published artifact", rejected.stderr)
                self.assertFalse(output.exists())
