"""Run mobile analysis/tests in a temporary native filesystem (e.g. WSL /tmp).

Flutter's shader compiler and file-copy operations may reject Windows-mounted
paths. Only source/configuration is staged; dependencies are resolved normally,
and no SDK files or compiler behavior are patched.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

MOBILE = Path(__file__).resolve().parents[1] / "mobile"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flutter", default="flutter")
    parser.add_argument("--temp-dir", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    flutter = shutil.which(args.flutter)
    if not flutter:
        parser.error("Flutter SDK executable was not found")
    dart = Path(flutter).resolve().parent / "cache/dart-sdk/bin/dart"
    with tempfile.TemporaryDirectory(prefix="cybersecra-mobile-", dir=args.temp_dir) as directory:
        target = Path(directory)
        for name in ("lib", "test"):
            shutil.copytree(MOBILE / name, target / name)
        for name in ("pubspec.yaml", "pubspec.lock", "analysis_options.yaml"):
            if (MOBILE / name).exists():
                shutil.copyfile(MOBILE / name, target / name)
        commands = [
            [flutter, "pub", "get", *(["--offline"] if args.offline else [])],
            [str(dart), "analyze"],
            [flutter, "test", "--no-pub", "--concurrency=1"],
        ]
        for command in commands:
            print("Running: " + " ".join(command), flush=True)
            subprocess.run(command, cwd=target, check=True)


if __name__ == "__main__":
    main()
