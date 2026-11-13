"""Show the patient UI on the 2.8" LCD, with the knob as input.

Chromium renders the built UI (dist/) invisibly at 320 x 240. Whenever the
picture changes it is sent to the LCD through the team's working startup
driver (medlock_home.py), the same way Measuring/scripts/mirror_pi_display.py
mirrors the measuring app. The driver file is read, never edited.

Knob: turning moves the highlight between buttons, pressing taps it.
Touch is not used (the team's touch input is still unreliable).

Build on the Mac with `npm run build`, copy dist/ next to this pi/ folder,
then on the Pi:

    python3 pi/mirror_ui.py --take-over

Ctrl+C stops it and restarts the original home screen.
Without the LCD (e.g. on a laptop): --no-lcd --no-knob --save-frame frame.png
"""
import argparse
import base64
import fcntl
import functools
import http.server
import io
import json
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PIL import Image

from lcd import HEIGHT, WIDTH, Lcd

UI_DIR = Path(__file__).resolve().parents[1] / 'dist'
CHROMIUM_LOG = Path.home() / 'medlock-chromium.log'
REPLY_TIMEOUT = 60  # seconds; a Pi 3B can be slow on first start


class Browser:
    """Headless Chromium driven over --remote-debugging-pipe (standard library only)."""

    def __init__(self, binary):
        to_child, self._out = os.pipe()
        self._in, from_child = os.pipe()

        def pipe_fds():  # Chromium reads commands on fd 3 and writes replies on fd 4
            a = fcntl.fcntl(to_child, fcntl.F_DUPFD, 10)
            b = fcntl.fcntl(from_child, fcntl.F_DUPFD, 10)
            os.dup2(a, 3)
            os.dup2(b, 4)

        self.profile = tempfile.mkdtemp(prefix='medlock-chromium-')
        self._log = CHROMIUM_LOG.open('w')
        self.proc = subprocess.Popen(
            [binary, '--headless=new', '--remote-debugging-pipe', '--no-first-run',
             '--no-default-browser-check', '--disable-gpu', '--hide-scrollbars', '--mute-audio',
             f'--user-data-dir={self.profile}', f'--window-size={WIDTH},{HEIGHT}', 'about:blank'],
            preexec_fn=pipe_fds, pass_fds=(3, 4),
            stdout=self._log, stderr=self._log)
        os.close(to_child)
        os.close(from_child)
        self._buffer = b''
        self._next_id = 0
        self._lock = threading.Lock()
        self.session = None
        target = self.call('Target.createTarget', {'url': 'about:blank'}, page=False)['targetId']
        self.session = self.call('Target.attachToTarget', {'targetId': target, 'flatten': True},
                                 page=False)['sessionId']
        self.call('Emulation.setDeviceMetricsOverride',
                  {'width': WIDTH, 'height': HEIGHT, 'deviceScaleFactor': 1, 'mobile': False})
        # alert() would freeze a headless page; the clinic-contact buttons still use it.
        self.call('Page.enable')
        self.call('Page.addScriptToEvaluateOnNewDocument', {'source': 'window.alert = () => {}'})

    def call(self, method, params=None, page=True):
        with self._lock:
            self._next_id += 1
            message = {'id': self._next_id, 'method': method, 'params': params or {}}
            if page:
                message['sessionId'] = self.session
            os.write(self._out, json.dumps(message).encode() + b'\0')
            while True:
                reply = self._read(method)
                if reply.get('id') == self._next_id:
                    if 'error' in reply:
                        raise RuntimeError(f"{method}: {reply['error'].get('message')}")
                    return reply.get('result', {})

    def _read(self, method):
        while b'\0' not in self._buffer:
            if not select.select([self._in], [], [], REPLY_TIMEOUT)[0]:
                raise RuntimeError(f'Chromium did not answer {method} within {REPLY_TIMEOUT} s. '
                                   f'Its messages are in {CHROMIUM_LOG}')
            chunk = os.read(self._in, 1 << 16)
            if not chunk:
                raise RuntimeError('Chromium closed unexpectedly.')
            self._buffer += chunk
        raw, self._buffer = self._buffer.split(b'\0', 1)
        return json.loads(raw)

    def evaluate(self, expression):
        return self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True})['result'].get('value')

    def open(self, url, timeout=120):
        self.call('Page.navigate', {'url': url})
        deadline = time.monotonic() + timeout
        while not self.evaluate("document.readyState === 'complete' && !!document.querySelector('.device')"):
            if time.monotonic() > deadline:
                state = self.evaluate("document.readyState + ', screen drawn: ' + !!document.querySelector('#root > *')")
                raise RuntimeError(f'The UI did not load from {url} ({state}). See {CHROMIUM_LOG}')
            time.sleep(0.5)

    def screenshot(self):
        return base64.b64decode(self.call('Page.captureScreenshot', {'format': 'png'})['data'])

    def key(self, name, shift=False):
        codes = {'Tab': 9, 'Enter': 13}
        down = {'type': 'keyDown', 'text': '\r'} if name == 'Enter' else {'type': 'rawKeyDown'}
        for event in (down, {'type': 'keyUp'}):
            self.call('Input.dispatchKeyEvent', {**event, 'key': name, 'code': name,
                                                 'windowsVirtualKeyCode': codes[name],
                                                 'modifiers': 8 if shift else 0})

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        shutil.rmtree(self.profile, ignore_errors=True)
        self._log.close()


def attach_knob(browser, changed, args):
    from gpiozero import Button, RotaryEncoder

    def press(name, shift=False):
        browser.key(name, shift)
        changed.set()

    forward, backward = (lambda: press('Tab')), (lambda: press('Tab', shift=True))
    encoder = RotaryEncoder(args.knob_a, args.knob_b, max_steps=0)
    encoder.when_rotated_clockwise = backward if args.reverse else forward
    encoder.when_rotated_counter_clockwise = forward if args.reverse else backward
    button = Button(args.knob_button, pull_up=not args.button_active_high, bounce_time=0.05)
    button.when_pressed = lambda: press('Enter')
    return encoder, button


def serve_ui():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(UI_DIR))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}/'


def main():
    p = argparse.ArgumentParser(description='Show the MedLock patient UI on the 2.8" LCD')
    p.add_argument('--repo', type=Path, default=Path.home() / 'MedLock', help='Team repo (for mirror_pi_display.py)')
    p.add_argument('--driver', type=Path, default=Path('/home/medlock/medlock_home.py'))
    p.add_argument('--take-over', action='store_true', help='Temporarily stop the home-screen program')
    p.add_argument('--url', help='Show this page instead of dist/ (e.g. http://127.0.0.1:8768/ from medlock_bridge.py)')
    p.add_argument('--verdict', choices=['pass', 'fix', 'unable'], default='pass',
                   help='Mock result for "Check syringe" (mock build only)')
    p.add_argument('--chromium', help='Chromium binary (default: chromium or chromium-browser)')
    p.add_argument('--knob-a', type=int, default=5)
    p.add_argument('--knob-b', type=int, default=6)
    p.add_argument('--knob-button', type=int, default=13)
    p.add_argument('--reverse', action='store_true', help='Swap knob turning direction')
    p.add_argument('--button-active-high', action='store_true', help='Knob press reads high instead of low')
    p.add_argument('--no-lcd', action='store_true', help='Do not use the LCD (testing)')
    p.add_argument('--no-knob', action='store_true', help='Do not use the knob (testing)')
    p.add_argument('--save-frame', type=Path, help='Also save the latest frame as a PNG')
    args = p.parse_args()

    binary = args.chromium or shutil.which('chromium') or shutil.which('chromium-browser')
    if not binary:
        p.error('Chromium not found. Pass --chromium /path/to/chromium.')
    if not args.url and not (UI_DIR / 'index.html').exists():
        p.error(f'No built UI in {UI_DIR}. Run `npm run build` on the Mac and copy dist/ here.')

    browser = lcd = server = None
    knob = None
    started = time.monotonic()
    step = lambda text: print(f'[{time.monotonic() - started:5.1f}s] {text}', flush=True)
    try:
        step(f'Starting Chromium ({binary})…')
        browser = Browser(binary)  # start before any other threads (it forks)
        step('Chromium is ready.')
        if args.url:
            url = args.url
        else:
            server, url = serve_ui()
        step(f'Loading the UI from {url}…')
        browser.open(url)
        step('UI loaded.')
        # Hide the dev panel so the knob never tabs into it; pick the mock result.
        browser.evaluate("""(() => {
            const s = document.createElement('style'); s.textContent = '.dev{display:none!important}';
            document.head.append(s);
            const r = [...document.querySelectorAll('.dev-radio')].find(l => l.textContent.trim() === %s);
            r?.querySelector('input').click();
        })()""" % json.dumps(args.verdict))
        if not args.no_lcd:
            step('Taking over the little screen…')
            lcd = Lcd(args.repo, args.driver, args.take_over)
        changed = threading.Event()
        if not args.no_knob:
            knob = attach_knob(browser, changed, args)
        print('MedLock UI is on the little screen. Turn the knob to move, press to select. Ctrl+C to stop.',
              flush=True)

        previous = None
        while True:
            png = browser.screenshot()
            if png != previous:
                previous = png
                frame = Image.open(io.BytesIO(png)).convert('RGB')
                if frame.size != (WIDTH, HEIGHT):
                    frame = frame.resize((WIDTH, HEIGHT))
                if lcd:
                    lcd.show(frame)
                if args.save_frame:
                    frame.save(args.save_frame)
            changed.wait(0.2)
            changed.clear()
    finally:
        if knob:
            for device in knob:
                device.close()
        if lcd:
            lcd.close()
        if browser:
            browser.close()
        if server:
            server.shutdown()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt))
    try:
        main()
    except KeyboardInterrupt:
        print('Stopped.')
    except Exception as exc:
        print(f'MedLock UI display stopped: {exc}', file=sys.stderr)
        sys.exit(1)
