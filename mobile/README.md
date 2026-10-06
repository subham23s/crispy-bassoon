# CyberSecRA-X mobile client

This Flutter client talks to the same backend as the web dashboard. It includes:

- registration, login, persisted-session restoration, access-token refresh, and server-side logout;
- protected evidence queries at `POST /chat/query`;
- protected document listing/upload at `GET /documents` and `POST /documents/upload`;
- protected log and IOC triage at `POST /logs/analyze` and `POST /ioc/analyze`;
- research workspace access, paper/vulnerability/threat/timeline/graph/evaluation views through the same API;
- workspace creation/selection, saved questions, research notes, and evidence bookmarks in `lib/workspace_page.dart`;
- saved answer history, source URLs, claim explanations, conflicts, and limitations;
- owner-scoped document deletion and explicit quarantine status;
- public API checks at `GET /health` and `GET /health/detailed`;
- file-picker and camera uploads, plus speech-to-text query input.

## Configuration

The API URL is compile-time configuration. Do not put credentials or API keys in the app.

```bash
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

`API_BASE_URL` defaults to `http://10.0.2.2:8000`, which is the Android emulator's
route to a backend on the host. Use a LAN-reachable HTTPS URL for a physical
device. For an iOS simulator, use `http://127.0.0.1:8000` when the backend is
running on the host, or another simulator-reachable URL. The request timeout can
be changed with `--dart-define=API_TIMEOUT_SECONDS=30`.

The default local HTTP URL is for development only. Use HTTPS outside a local
emulator/simulator workflow. The secure storage plugin holds only access and
refresh tokens; it never stores provider credentials.

## Platform projects

The repository intentionally keeps the Dart source independent of generated
platform folders. If `android/` and `ios/` are absent, generate them on a
machine with Flutter installed using the safe helper:

```bash
cd mobile
tool/generate_platforms.sh
flutter pub get
```

The helper creates a temporary Flutter scaffold, copies only its generated
`android/` and `ios/` folders, adds the Internet/camera/microphone/speech
permission declarations, and refuses to overwrite existing platform folders or
`lib/`. It does not run a build. Remove or review the generated platform folders
before committing them, especially signing and release settings.

Android/iOS scaffolds are now present. If a checkout contains only generated
plugin-output folders or otherwise lacks scaffold files, use
`bash tool/generate_platforms.sh --fill-missing` to add missing files while
preserving existing ones. The helper also ensures root-level iOS usage
descriptions and Android capture/speech-service permissions.

## Checks

From the repository root, run the deterministic environment report:

```bash
python3 scripts/check_mobile.py
```

It reports Flutter/Dart availability and prints the exact mobile commands that
are blocked when the SDK or generated platform folders are missing. A Flutter
build, analyzer, test, or device run has not been claimed unless those commands
are run in an environment with the required SDK, dependencies, platform tools,
and backend.

Flutter 3.47.6/Dart 3.13.5 locally passed clean analysis and six tests, covering workspace notes, the defensive tools page, API configuration, and session preservation after a refreshed request returns 403. Android/iOS builds remain unverified because their platform toolchains are unavailable.

On WSL/Windows-mounted paths that reject shader compilation or native file-copy operations, stage source on a native filesystem:

```bash
# Repository root; select an existing native temp directory with sufficient space.
python3 scripts/check_mobile_portable.py \
  --flutter /path/to/flutter/bin/flutter --temp-dir /tmp
```

The helper resolves dependencies, runs Dart analysis, and runs ordinary Flutter tests with shaders enabled. `--offline` is available when dependencies are already cached. CI provisions Flutter and runs the normal analysis/test commands directly.
