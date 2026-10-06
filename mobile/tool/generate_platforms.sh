#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fill_missing=false
if [[ "${1:-}" == "--fill-missing" && $# -eq 1 ]]; then
  fill_missing=true
elif [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--fill-missing]" >&2
  exit 2
fi

if ! command -v flutter >/dev/null 2>&1; then
  echo "BLOCKED: flutter create --no-pub --platforms=android,ios --project-name=cybersecra_x_mobile <temporary-directory>" >&2
  echo "Install Flutter 3.22+ and rerun this helper from mobile/." >&2
  exit 2
fi

for platform in android ios; do
  platform_dir="$ROOT/$platform"
  if [[ -e "$platform_dir" && ! -d "$platform_dir" ]]; then
    echo "Refusing to overwrite mobile/$platform because it is not a directory." >&2
    exit 2
  fi
  if [[ "$fill_missing" == false && -d "$platform_dir" ]] && find "$platform_dir" -type f -print -quit | grep -q .; then
    echo "Refusing to overwrite existing mobile/$platform platform files." >&2
    echo "Review/remove that folder explicitly, then rerun this helper if regeneration is intended." >&2
    exit 2
  fi
done

# Empty placeholder folders are safe to remove; generated files and lib/ are not.
rmdir "$ROOT/android" "$ROOT/ios" 2>/dev/null || true

if [[ ! -d "$ROOT/lib" ]]; then
  echo "Refusing to generate platforms because mobile/lib is missing." >&2
  exit 2
fi

scratch="$(mktemp -d "${TMPDIR:-/tmp}/cybersecra-x-platforms.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

target="$scratch/project"
flutter create \
  --no-pub \
  --platforms=android,ios \
  --project-name=cybersecra_x_mobile \
  "$target"

[[ -d "$target/android" && -d "$target/ios" ]] || {
  echo "Flutter did not generate both Android and iOS platform folders." >&2
  exit 1
}

python3 - "$target" "$ROOT" <<'PY'
from pathlib import Path
import shutil
import sys

source, destination = map(Path, sys.argv[1:])
for platform in ("android", "ios"):
    for path in (source / platform).rglob("*"):
        target = destination / path.relative_to(source)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            shutil.copyfile(path, target)
            try:
                target.chmod(path.stat().st_mode & 0o777)
            except PermissionError:
                pass  # Some Windows mounts do not support chmod.
metadata = source / ".metadata"
if metadata.exists() and not (destination / ".metadata").exists():
    shutil.copyfile(metadata, destination / ".metadata")
PY

python3 - "$ROOT" <<'PY'
from pathlib import Path
import plistlib
import re
import sys

root = Path(sys.argv[1])
manifest = root / "android/app/src/main/AndroidManifest.xml"
text = manifest.read_text(encoding="utf-8")
permissions = (
    '    <uses-permission android:name="android.permission.INTERNET" />',
    '    <uses-permission android:name="android.permission.CAMERA" />',
    '    <uses-permission android:name="android.permission.RECORD_AUDIO" />',
)
for permission in permissions:
    if permission not in text:
        text = re.sub(r"(<manifest\b[^>]*>)", r"\1\n" + permission, text, count=1)
if "android:usesCleartextTraffic=" not in text:
    text = text.replace(
        "<application",
        '<application\n        android:usesCleartextTraffic="true"',
        1,
    )
text = text.replace('android:label="cybersecra_x_mobile"', 'android:label="CyberSecRA-X"')
if "android.speech.RecognitionService" not in text:
    query = '        <intent><action android:name="android.speech.RecognitionService" /></intent>'
    if "<queries>" in text:
        text = text.replace("<queries>", "<queries>\n" + query, 1)
    else:
        text = text.replace("</manifest>", "    <queries>\n" + query + "\n    </queries>\n</manifest>", 1)
manifest.write_text(text, encoding="utf-8")

plist = root / "ios/Runner/Info.plist"
data = plistlib.loads(plist.read_bytes())
entries = {
    "NSCameraUsageDescription": "Camera capture is used to upload evidence documents.",
    "NSMicrophoneUsageDescription": "Microphone access is used for voice queries.",
    "NSSpeechRecognitionUsageDescription": "Speech recognition is used to transcribe voice queries.",
}
for key, value in entries.items():
    data.setdefault(key, value)
if data.get("CFBundleDisplayName") == "Cybersecra X Mobile":
    data["CFBundleDisplayName"] = "CyberSecRA-X"
plist.write_bytes(plistlib.dumps(data, sort_keys=False))
PY

echo "Generated mobile/android and mobile/ios without modifying mobile/lib."
echo "Next: cd mobile && flutter pub get && flutter analyze"
