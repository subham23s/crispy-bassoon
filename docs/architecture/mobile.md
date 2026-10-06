# Mobile architecture

Flutter uses the same REST API as the web client. `ApiService` stores only the access token in `flutter_secure_storage`; API keys never enter the mobile bundle.

- `AuthGate`: registration/login and secure token acquisition.
- `HomeShell`: mobile bottom navigation.
- `AskPage`: text and speech-to-text query, evidence/CERS/claim panels.
- `ToolsPage`: defensive log and IOC analysis.
- `LibraryPage`: file picker and camera capture upload to document ingestion.
- `DashboardPage`: API health and research actions.

Configure a physical device with `flutter run --dart-define=API_BASE_URL=https://your-api.example`. Android emulators use `10.0.2.2`; iOS simulators use a host-reachable URL.
