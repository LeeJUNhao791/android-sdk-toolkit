#!/usr/bin/env python3
"""Publish a Gradle SDK to a fresh local Maven repository and verify a consumer."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def handoff(args):
    fields = args.coordinate.split(":")
    token = r"[A-Za-z0-9_][A-Za-z0-9_.-]*"
    group_pattern = r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*"
    if len(fields) != 3 or not all(
        re.fullmatch(pattern, value) for pattern, value in zip((group_pattern, token, token), fields)
    ):
        raise ValueError("Expected Maven coordinate group:artifact:version.")
    group, artifact, version = fields
    producer = args.producer.resolve()
    consumer = args.consumer.resolve()
    if not producer.is_dir() or not consumer.is_dir() or producer == consumer:
        raise ValueError("Provide separate existing producer and consumer directories.")
    wrapper = (args.wrapper or producer).resolve() / "gradle/wrapper/gradle-wrapper.jar"
    if not wrapper.is_file():
        raise ValueError(f"Gradle wrapper JAR not found: {wrapper}")
    output = args.output.resolve()
    if output.exists():
        raise ValueError(f"Choose a new output directory: {output}")
    java_home = os.environ.get("JAVA_HOME")
    executable = "java.exe" if os.name == "nt" else "java"
    java = str(Path(java_home) / "bin" / executable) if java_home else executable
    gradle = [java, "-classpath", str(wrapper), "org.gradle.wrapper.GradleWrapperMain"]
    artifact_path = Path(*group.split("."), artifact, version, f"{artifact}-{version}.{args.kind}")
    pom_path = artifact_path.with_suffix(".pom")
    verify_task = {"aar": "assembleDebug", "jar": "run"}[args.kind]
    consumer_check = Path(__file__).resolve().with_name("verify_consumer.gradle")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sdk-handoff-", dir=output.parent) as directory:
        repo = Path(directory) / "repo"
        properties = [f"-PtoolkitRepo={repo}", f"-PtoolkitCoordinate={args.coordinate}"]
        subprocess.run(
            [*gradle, *properties, "publishAllPublicationsToHandoffRepository"],
            cwd=producer, stdout=sys.stderr, check=True,
        )
        if not (repo / artifact_path).is_file() or not (repo / pom_path).is_file():
            raise ValueError(f"Missing published artifact and POM for {args.coordinate}.")
        subprocess.run(
            [*gradle, *properties, "--init-script", str(consumer_check),
             f"-PtoolkitExpectedArtifact={repo / artifact_path}", ":verifySdkHandoff", verify_task],
            cwd=consumer, stdout=sys.stderr, check=True,
        )
        repo.rename(output)
    return {
        "status": "pass",
        "coordinate": args.coordinate,
        "artifact": str(output / artifact_path),
        "pom": str(output / pom_path),
        "consumer_task": verify_task,
        "consumer_artifact_verified": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("producer", type=Path, help="Gradle producer project.")
    parser.add_argument("consumer", type=Path, help="Separate Gradle smoke-test project.")
    parser.add_argument("--kind", choices=("aar", "jar"), required=True)
    parser.add_argument("--coordinate", required=True, help="Published group:artifact:version.")
    parser.add_argument("--output", type=Path, required=True, help="New local Maven repository directory.")
    parser.add_argument("--wrapper", type=Path, help="Gradle wrapper project (defaults to producer).")
    args = parser.parse_args()
    try:
        result = handoff(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"SDK handoff error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
