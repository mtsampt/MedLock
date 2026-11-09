# MedLock guided station UI

React/Vite view of the unified Python station controller. Targets a 320 × 240 touchscreen. Preparation progress and checks come from the backend; there are no automatic mock results.

Build with npm ci && npm run build. Start the backend from Measuring with python -m medlock_device --replay outputs/medlock-pilot-2026-10-21/images and open http://127.0.0.1:8767/. For development, npm run dev proxies /api to that same backend.

Protocol content is shared from Measuring/medlock_device/protocol.json. The server owns navigation, manual supplies confirmation, check/retry and session state. No dose time is invented. Volume and combined pass remain unavailable without actual calibration and configured target/tolerance.

See ../docs/INTEGRATION.md for deployment, ../docs/API.md for API details, and ../INTEGRATION_PLAN.md for the project plan.
