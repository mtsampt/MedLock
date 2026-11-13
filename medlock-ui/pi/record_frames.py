"""Record every screen of the patient UI as pictures, for the 2.8" panel demo.

Run this on the Mac (Chromium is far too slow on the Pi 3B). It opens the
built UI (dist/) in headless Chrome at 320 x 240 and explores it the way the
knob would: Tab (turn forward), Shift+Tab (turn back) and Enter (press).
Each distinct picture becomes a state; the keys between them become edges.
pi/show_frames.py plays the result on the Pi.

    npm run build
    python3 pi/record_frames.py --chromium "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

Output: pi/frames/<verdict>/NNN.png and graph.json, one folder per mock
result (pass, fix, unable). The Start screen's dose time is frozen at the
moment of recording.
"""
import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

from mirror_ui import UI_DIR, Browser, serve_ui

FRAMES_DIR = Path(__file__).resolve().parent / 'frames'
ACTIONS = {'next': ('Tab', False), 'prev': ('Tab', True), 'press': ('Enter', False)}
MAX_STATES = 400

SETUP = """(() => {
    const s = document.createElement('style');
    s.textContent = '.dev{display:none!important} *{transition:none!important;animation:none!important}';
    document.head.append(s);
    const r = [...document.querySelectorAll('.dev-radio')].find(l => l.textContent.trim() === %s);
    r?.querySelector('input').click();
})()"""


class Recorder:
    def __init__(self, browser, url, verdict):
        self.browser, self.url, self.verdict = browser, url, verdict
        self.path = None  # key path of the page as it is now

    def load(self):
        self.browser.open(self.url)
        self.browser.evaluate(SETUP % json.dumps(self.verdict))
        self.path = []
        return self.settle()

    def settle(self, timeout=15):
        """Wait until the check spinner is gone and two pictures in a row match."""
        deadline = time.monotonic() + timeout
        previous = None
        while True:
            busy = self.browser.evaluate("!!document.querySelector('.spinner')")
            png = self.browser.screenshot()
            if not busy and png == previous:
                return png
            if time.monotonic() > deadline:
                raise RuntimeError(f'Screen did not settle after {self.path}')
            previous = png
            time.sleep(0.1)

    def act(self, action):
        """Press a knob action. Returns (picture, checking picture or None)."""
        self.browser.key(*ACTIONS[action])
        self.path.append(action)
        busy = None
        time.sleep(0.05)
        if self.browser.evaluate("!!document.querySelector('.spinner')"):
            busy = self.browser.screenshot()
        return self.settle(), busy

    def goto(self, path):
        if self.path == path:
            return
        self.load()
        for action in path:
            self.act(action)


def record(browser, url, verdict, out):
    rec = Recorder(browser, url, verdict)
    ids, pngs, paths, edges = {}, [], [], []

    def state_of(png, path):
        # The Help overlay looks the same on every screen, so the text behind it is part of the identity.
        behind = rec.browser.evaluate("document.querySelector('.screen')?.innerText || ''")
        key = hashlib.sha1(png + behind.encode()).hexdigest()
        if key not in ids:
            if len(pngs) >= MAX_STATES:
                raise RuntimeError(f'More than {MAX_STATES} screens; something is not settling.')
            ids[key] = len(pngs)
            pngs.append(png)
            paths.append(list(path))
            edges.append({})
            pending.extend((ids[key], a) for a in ('press', 'prev', 'next'))
        return ids[key]

    pending = []
    current = state_of(rec.load(), [])
    while pending:
        # Prefer work on the screen that is already showing; otherwise replay a path.
        mine = [i for i, (s, _) in enumerate(pending) if s == current]
        source, action = pending.pop(mine[-1] if mine else 0)
        if source != current:
            rec.goto(paths[source])
        png, busy = rec.act(action)
        current = state_of(png, paths[source] + [action])
        rec.path = list(paths[current])  # same picture, so treat it as the shortest known route
        edges[source][action] = current
        if busy:
            edges[source][action + '_via'] = 'checking.png'
            (out / 'checking.png').write_bytes(busy)
        print(f'\r  {verdict}: {len(pngs)} screens, {len(pending)} moves left   ', end='', flush=True)
    print()

    for i, png in enumerate(pngs):
        (out / f'{i:03d}.png').write_bytes(png)
    graph = {'start': '000', 'states': {f'{i:03d}': {a: (f'{t:03d}' if isinstance(t, int) else t)
                                                     for a, t in e.items()} for i, e in enumerate(edges)}}
    (out / 'graph.json').write_text(json.dumps(graph, indent=1))


def main():
    p = argparse.ArgumentParser(description='Record the patient UI screens for the panel demo')
    p.add_argument('--chromium', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    p.add_argument('--verdict', choices=['pass', 'fix', 'unable', 'all'], default='all')
    args = p.parse_args()
    if not (UI_DIR / 'index.html').exists():
        p.error(f'No built UI in {UI_DIR}. Run `npm run build` first.')

    browser = Browser(args.chromium)
    # Freeze the clock so the Start countdown and Done's "Logged at" can't change mid-recording.
    frozen = int(time.time() * 1000)
    browser.call('Page.addScriptToEvaluateOnNewDocument', {'source': f'''
        Date = class extends Date {{
            constructor(...a) {{ super(...(a.length ? a : [{frozen}])) }}
            static now() {{ return {frozen} }}
        }}'''})
    server, url = serve_ui()
    try:
        for verdict in (['pass', 'fix', 'unable'] if args.verdict == 'all' else [args.verdict]):
            out = FRAMES_DIR / verdict
            shutil.rmtree(out, ignore_errors=True)
            out.mkdir(parents=True)
            record(browser, url, verdict, out)
    finally:
        browser.close()
        server.shutdown()
    print(f'Saved to {FRAMES_DIR}')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
