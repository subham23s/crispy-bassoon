#!/usr/bin/env python3
"""Deterministically report the local Flutter mobile prerequisites.

This checker does not install packages, contact the network, start a backend, or
claim a build. A non-zero result means one or more concrete mobile commands are
blocked by this machine's environment.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile"


def availability(command: str) -> bool:
    return shutil.which(command) is not None


def report() -> dict[str, object]:
    flutter = availability("flutter")
    dart = availability("dart")
    # Empty placeholder folders are not usable Flutter platform projects.
    android = (MOBILE / "android/app/src/main/AndroidManifest.xml").is_file()
    ios = (MOBILE / "ios/Runner/Info.plist").is_file()
    sdk_candidates = [Path(value) for value in (os.getenv("ANDROID_HOME"), os.getenv("ANDROID_SDK_ROOT")) if value]
    sdk_candidates.append(Path.home() / "Android/Sdk")
    local_properties = MOBILE / "android/local.properties"
    if local_properties.is_file():
        for line in local_properties.read_text(encoding="utf-8").splitlines():
            if line.startswith("sdk.dir="):
                sdk_candidates.append(Path(line.split("=", 1)[1]))
    android_sdk = any((path / "platform-tools/adb").is_file() and (path / "platforms").is_dir() for path in sdk_candidates)
    java_home = os.getenv("JAVA_HOME")
    java = availability("java") or bool(java_home and (Path(java_home) / "bin/java").is_file())
    xcode = sys.platform == "darwin" and availability("xcodebuild")

    blocked: list[dict[str, str]] = []

    def block(command: str, reason: str) -> None:
        blocked.append({"command": command, "reason": reason})

    sdk_reason = "Flutter SDK is not available on PATH."
    if not flutter:
        for command in (
            "cd mobile && flutter pub get",
            "cd mobile && flutter analyze",
            "cd mobile && flutter test",
            "cd mobile && flutter build apk --debug",
            "cd mobile && flutter build ios --no-codesign",
            "cd mobile && flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000",
        ):
            block(command, sdk_reason)
        block(
            "cd mobile && tool/generate_platforms.sh",
            "Flutter SDK is required to run the platform generator.",
        )
        block(
            "flutter create --no-pub --platforms=android,ios --project-name=cybersecra_x_mobile <temporary-directory>",
            "Flutter SDK is not available to create platform folders.",
        )

    if not dart:
        block("cd mobile && dart analyze", "Dart SDK is not available on PATH.")

    if flutter and (not android or not ios):
        platform_reason = "Generated Android/iOS platform folders are missing."
        if not android:
            block("cd mobile && flutter build apk --debug", platform_reason)
        if not ios:
            block("cd mobile && flutter build ios --no-codesign", platform_reason)
        block(
            "cd mobile && flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000",
            platform_reason,
        )

    if flutter and android and (not android_sdk or not java):
        reason = "Android SDK (platforms/platform-tools) is missing." if not android_sdk else "Java runtime is missing."
        block("cd mobile && flutter build apk --debug", reason)
    if flutter and ios and not xcode:
        block("cd mobile && flutter build ios --no-codesign", "iOS builds require macOS and Xcode.")

    return {
        "project": "mobile",
        "flutter_available": flutter,
        "dart_available": dart,
        "android_platform_present": android,
        "ios_platform_present": ios,
        "android_sdk_present": android_sdk,
        "java_available": java,
        "ios_toolchain_available": xcode,
        "blocked_commands": blocked,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the same report as stable JSON instead of human-readable text",
    )
    args = parser.parse_args()
    result = report()

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print("Mobile environment report")
        print(f"project: {result['project']}")
        print(f"flutter: {'available' if result['flutter_available'] else 'unavailable'}")
        print(f"dart: {'available' if result['dart_available'] else 'unavailable'}")
        print(
            "platform projects: "
            f"android={'present' if result['android_platform_present'] else 'missing'}, "
            f"ios={'present' if result['ios_platform_present'] else 'missing'}"
        )
        blocked = result["blocked_commands"]
        if blocked:
            print("blocked commands:")
            for item in blocked:
                print(f"- {item['command']}  # {item['reason']}")
        else:
            print("blocked commands: none detected")
        print("No Flutter build, test, or device run is claimed by this checker.")

    return 2 if result["blocked_commands"] else 0


if __name__ == "__main__":
    sys.exit(main())
