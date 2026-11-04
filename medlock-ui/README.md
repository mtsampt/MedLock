# MedLock station UI

Patient-facing touchscreen UI for the MedLock IVF medication-preparation station (Pregnyl trigger shot flow). React + Vite, sized for a 320×240 2.8" display (landscape).

## Run it

```bash
npm install
npm run dev
```

Open http://localhost:5173. The screen is shown at its real 1:1 size (320×240); use browser zoom (⌘+) to inspect it on a laptop. With no backend configured, a **dev panel** appears next to the screen. Use it to jump between screens and choose what the next syringe check returns (pass / fix / unable).

## Connect the real backend

Create a `.env` file:

```
VITE_API_URL=http://<pi-or-laptop-ip>:8000
```

The dev panel hides itself and the UI calls the FastAPI server instead. The expected endpoints are documented at the top of `src/api.js`. Agree on that contract with whoever owns the backend before either side builds too far.

## Where things live

| File | What it is |
|---|---|
| `src/protocol.js` | Medication, supplies, and prep steps as data. Edit steps here, not in screens. |
| `src/api.js` | The only file that talks to the backend. Also holds the mock. |
| `src/App.jsx` | The screen flow (which screen comes next). |
| `src/components/Frame.jsx` | Shared layout: progress bar, Help, Back, primary button. |
| `src/screens/` | One file per screen. |
| `src/styles.css` | All styling. Colors and sizes are tokens at the top. |

## Design rules built in

- One action per screen; progress shown as "Step X of N".
- The patient confirms each supply (Yes / No), one item at a time.
- Touch targets at least 48px tall (Help 44px).
- Every result uses color + symbol + text.
- "Needs a fix" always says what to do, and loops back to the syringe check.
- Any backend error or unknown response shows "Couldn't check," never a pass.

## Running on the Pi

```bash
npm run build
npx vite preview --host
chromium-browser --kiosk --force-device-scale-factor=1 http://localhost:4173
```

## Before using with anyone

The prep steps in `protocol.js` are placeholders for a simulated training prototype. Confirm the real sequence and volumes with your clinician contact.
