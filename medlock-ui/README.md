# MedLock station UI

Patient UI for the MedLock station, sized for the 2.8" screen (320×240).

## Run it on a laptop

```bash
npm install
npm run dev
```

Open http://localhost:5173. The panel next to the screen lets you jump between screens and pick the syringe check result (pass / fix / unable).

## Run it on the Pi's 2.8" screen

The Pi plays pictures of each screen that were recorded on a laptop. The knob works like the real UI: turn to move, press to select. Results are practice results, not the camera.

```bash
cd ~/MedLock/medlock-ui
python3 pi/show_frames.py --take-over --still pi/frames/pass/000.png   # screen test: one picture
python3 pi/show_frames.py --take-over                                  # whole flow with the knob
```

Ctrl+C stops it and brings back the normal home screen.

| Option | Use it when |
|---|---|
| `--verdict fix` / `--verdict unable` | Show the other result screens |
| `--reverse` | The knob turns the wrong way |
| `--button-active-high` | Pressing the knob does nothing |
| `--keys` | Use the keyboard instead: `n` next, `p` back, Enter select, `q` quit |

## After changing the UI

Re-record the pictures on a laptop with Google Chrome and Python (Pillow + NumPy):

```bash
npm run build
python3 pi/record_frames.py      # takes about 30 min
```

Then copy `dist/` and `pi/` to `~/MedLock/medlock-ui` on the Pi.
