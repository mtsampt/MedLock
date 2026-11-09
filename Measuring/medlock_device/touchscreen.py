"""Native 320 × 240 view of the same controller used by React."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 240
FONTS = Path(__file__).parent / 'fonts'


@lru_cache(maxsize=32)
def font(size, bold=False):
    return ImageFont.truetype(str(FONTS / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')), size)


def view(state):
    """Presentation only; every action is validated by Session."""
    screen, protocol = state['screen'], state['protocol']
    title, detail, actions = '', '', []
    tone = '#2b567c'
    if state['help_open']:
        title, detail = 'Station help', 'Keep the full barrel visible and still. Volume needs calibration. Bench prototype only.'
        actions = [('reset', 'Reset flow'), ('close_help', 'Back')]
    elif screen == 'start':
        title, detail = protocol['medication'], 'Bench preparation flow. Camera results are experimental.'
        actions = [('begin', 'Begin')]
    elif screen == 'supplies':
        item = protocol['supplies'][state['supply_index']]
        title = ('Get ' if state['missing'] else 'Do you have ') + item['label'].lower() + ('' if state['missing'] else '?')
        detail = f"Manual confirmation: {state['supply_index'] + 1} of {len(protocol['supplies'])}"
        actions = [('back', 'Back'), ('confirm', 'I have it now')] if state['missing'] else [('missing', 'No'), ('confirm', 'Yes')]
    elif screen == 'prep':
        prep = protocol['prep_steps'][state['prep_index']]
        title = prep['title']
        detail = prep['detail'] + (' ' + prep['warning'] if prep.get('warning') else '')
        actions = [('back', 'Back'), ('next', 'Done, next')]
    elif screen == 'check':
        title = 'Place syringe in dock'
        detail = 'Keep the full barrel visible and hold still.'
        if state['simulated']:
            detail = 'Seated in simulation. Uses a saved photo.' if state['seated'] else 'Tap Seat to simulate the dock sensor.'
            actions = [('seat', 'Unseat' if state['seated'] else 'Seat (demo)'), ('capture', 'Check syringe')]
        else:
            if not state['hardware_seat']:
                detail = 'Seat sensor unavailable. Configure hardware before checking.'
            actions = [('back', 'Back'), ('capture', 'Check syringe')]
    elif screen == 'checking':
        title, detail = 'Checking syringe…', 'Keep the syringe still. Camera and inference are running.'
    elif screen == 'result':
        result = state['result']
        if result['verdict'] == 'pass':
            title, detail, tone = 'Bench checks passed', 'Experimental result; not injection clearance.', '#2c774c'
            actions = [('reset', 'Reset'), ('complete', 'Continue')]
        else:
            title = 'Visible air detected' if result.get('air_detected') is True and result['verdict'] == 'fix' else 'No visible air' if result.get('reason_code') == 'volume_unverified' else 'Needs adjustment' if result['verdict'] == 'fix' else 'Unable to verify'
            detail = 'Volume not verified.' if result.get('reason_code') == 'volume_unverified' else result['reason']
            tone = '#a56b14'
            actions = [('reset', 'Reset'), ('retry', 'Check again')]
    elif screen == 'done':
        title, detail = 'Bench check recorded', 'This prototype result does not authorize an injection.'
        actions = [('reset', 'Finish')]
    if screen == 'result' and not state['help_open']:
        title = ('✓ ' if state['result']['verdict'] == 'pass' else '! ' if state['result']['verdict'] == 'fix' else '? ') + title
    buttons = []
    if not state['help_open']:
        buttons.append(dict(action='help', label='? Help', x=248, y=6, width=60, height=44))
    if not state['help_open'] and ((screen == 'supplies' and not state['missing']) or (screen == 'check' and state['simulated'])):
        buttons.append(dict(action='back', label='Back', x=180, y=6, width=60, height=44))
    for index, (action, label) in enumerate(actions):
        buttons.append(dict(action=action, label=label, x=12 + index * 152 if len(actions) == 2 else 12,
                            y=180, width=144 if len(actions) == 2 else 296, height=48))
    return dict(title=title, detail=detail, tone=tone, buttons=buttons)


class TouchUI:
    def __init__(self, session):
        self.session = session

    def snapshot(self):
        state = self.session.snapshot()
        return dict(state, **view(state))

    def action(self, action, expected=None):
        from .state_machine import FlowError
        state = expected or self.snapshot()
        if action not in {button['action'] for button in state['buttons']}:
            return False
        try:
            self.session.action(action, state['session_id'], state['revision'])
            return True
        except FlowError:
            return False

    def render(self):
        return render(self.snapshot())


def render(state):
    state = dict(state, **view(state))
    image = Image.new('RGB', (WIDTH, HEIGHT), '#fdfdfd')
    draw = ImageDraw.Draw(image)

    def lines(text, y, size, max_lines, bold=False, color='#20272b'):
        face = font(size, bold)
        rows, line = [], ''
        for word in text.split():
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=face) > 296 and line:
                rows.append(line)
                line = word
            else:
                line = candidate
        if line:
            rows.append(line)
        if len(rows) > max_lines:
            rows = rows[:max_lines]
            while rows[-1] and draw.textlength(rows[-1] + '…', font=face) > 296:
                rows[-1] = rows[-1][:-1]
            rows[-1] += '…'
        for index, row in enumerate(rows):
            draw.text((12, y + index * (size + 4)), row, font=face, fill=color)

    screen = state['screen']
    step = 0 if screen == 'start' else 1 if screen == 'supplies' else state['prep_index'] + 2 if screen == 'prep' else len(state['protocol']['prep_steps']) + 2
    draw.text((12, 12), 'MedLock' if not step else f"Step {step} of {len(state['protocol']['prep_steps']) + 2}", font=font(12, True), fill='#626b70')
    lines(state['title'], 56, 18, 2, bold=True, color=state['tone'])
    lines(state['detail'], 106, 12, 3)
    draw.text((12, 162), 'Photo replay · bench prototype' if state['simulated'] else 'Hardware · bench prototype', font=font(10), fill='#626b70')
    for button in state['buttons']:
        x, y, w, h = (button[key] for key in ('x', 'y', 'width', 'height'))
        secondary = button['action'] in {'help', 'back', 'reset', 'seat', 'missing'}
        draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=5, fill='#fdfdfd' if secondary else '#2b567c', outline='#d27a00' if state.get('focus_action') == button['action'] else '#cbd0d3', width=3 if state.get('focus_action') == button['action'] else 1)
        draw.text((x + w / 2, y + h / 2), button['label'], font=font(12 if button['action'] == 'help' else 14, True), fill='#20272b' if secondary else 'white', anchor='mm')
    return image
