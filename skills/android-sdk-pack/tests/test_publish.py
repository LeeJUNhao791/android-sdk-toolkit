import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish_sdk.py"
SPEC = importlib.util.spec_from_file_location("publish_sdk", SCRIPT)
publish_sdk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_sdk)


class SdkHandoff(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        producer = root / "producer"
        consumer = root / "consumer"
        wrapper = producer / "gradle/wrapper/gradle-wrapper.jar"
        wrapper.parent.mkdir(parents=True)
        wrapper.touch()
        consumer.mkdir()
        self.args = SimpleNamespace(
            producer=producer, consumer=consumer, wrapper=None, kind="aar", consumer_task=None,
            coordinate="example.device:sdk:1.0", output=root / "verified",
        )

    def publish_fixture(self, command, **_):
        path = next(option.split("=", 1)[1] for option in command if option.startswith("-PtoolkitRepo="))
        artifact = Path(path) / f"example/device/sdk/1.0/sdk-1.0.{self.args.kind}"
        artifact.parent.mkdir(parents=True)
        artifact.touch()
        artifact.with_suffix(".pom").touch()
        return Path(path)

    def test_consumer_uses_the_same_fresh_repository(self):
        for kind, task in (("aar", "assembleDebug"), ("jar", "run")):
            with self.subTest(kind=kind):
                self.args.kind = kind
                self.args.output = self.args.output.with_name(kind)
                commands = []

                def run(command, **kwargs):
                    commands.append(command)
                    if len(commands) == 1:
                        self.publish_fixture(command, **kwargs)

                with patch.object(publish_sdk.subprocess, "run", side_effect=run):
                    report = publish_sdk.handoff(self.args)
                self.assertEqual(len(commands), 2)
                self.assertIn("publishAllPublicationsToHandoffRepository", commands[0])
                self.assertIn(task, commands[1])
                self.assertIn(f"-PtoolkitConsumerTask={task}", commands[1])
                self.assertIn(":verifySdkHandoff", commands[1])
                init_script = Path(commands[1][commands[1].index("--init-script") + 1])
                self.assertTrue(init_script.is_file())
                expected = next(arg for arg in commands[1] if arg.startswith("-PtoolkitExpectedArtifact="))
                self.assertTrue(expected.endswith(f"sdk-1.0.{kind}"))
                self.assertEqual(
                    [arg for arg in commands[0] if arg.startswith("-PtoolkitRepo=")],
                    [arg for arg in commands[1] if arg.startswith("-PtoolkitRepo=")],
                )
                self.assertIn("-PtoolkitCoordinate=example.device:sdk:1.0", commands[1])
                self.assertTrue(report["consumer_artifact_verified"])
                self.assertTrue(Path(report["artifact"]).is_file())
                self.assertTrue(Path(report["pom"]).is_file())

    def test_consumer_failure_does_not_deliver_output(self):
        def run(command, **kwargs):
            if "assembleDebug" in command:
                raise subprocess.CalledProcessError(1, command)
            self.publish_fixture(command, **kwargs)

        with patch.object(publish_sdk.subprocess, "run", side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                publish_sdk.handoff(self.args)
        self.assertFalse(self.args.output.exists())

    def test_missing_artifact_stops_before_consumer(self):
        with patch.object(publish_sdk.subprocess, "run") as gradle:
            with self.assertRaisesRegex(ValueError, "artifact and POM"):
                publish_sdk.handoff(self.args)
        gradle.assert_called_once()
        self.assertFalse(self.args.output.exists())
