"""Native 320 × 240 view of the same controller used by React."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 320, 240
FONTS = Path(__file__).parent / 'fonts'
# Same tokens as medlock-ui/src/styles.css, so the LCD matches the patient UI design.
SURFACE, SURFACE_2, INK, INK_SOFT, LINE = '#ffffff', '#f2f4f8', '#1c2434', '#5b6678', '#dde2ea'
ACCENT, ACCENT_SOFT = '#2f5bd3', '#eaf0fd'
TONES = {'pass': ('#2e7d4f', '#e6f3ec', '✓'), 'fix': ('#b26a00', '#fdf1df', '!'), 'unable': ('#5a6472', '#eceef1', '?')}
RADIUS, PAD_X, FOOTER_Y = 14, 10, HEIGHT - 6 - 48
HELP_X, HELP_W = WIDTH - PAD_X - 84, 84
SECONDARY = {'help', 'back', 'reset', 'seat', 'missing'}


@lru_cache(maxsize=48)
def font(size, bold=False):
    """Inter (OFL) for text; bold=True or 'semibold'."""
    name = {True: 'Inter-Bold.ttf', 'semibold': 'Inter-SemiBold.ttf'}.get(bold, 'Inter-Regular.ttf')
    return ImageFont.truetype(str(FONTS / name), size)


@lru_cache(maxsize=16)
def symbol_font(size):
    # Inter's web build has no ✓ / ✕, so symbols come from the bundled DejaVu.
    return ImageFont.truetype(str(FONTS / 'DejaVuSans-Bold.ttf'), size)


def focus_ring(draw, button):
    """Knob highlight, as in the patient UI: inset ring, white on the blue primary button."""
    x, y, w, h = (button[key] for key in ('x', 'y', 'width', 'height'))
    colour = '#ffffff' if button.get('primary') else INK
    draw.rounded_rectangle((x + 5, y + 5, x + w - 6, y + h - 6), radius=16 if button['action'] == 'help' else 9,
                           outline=colour, width=3)


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
        buttons.append(dict(action='help', label='? Help', x=HELP_X, y=6, width=HELP_W, height=44, primary=False))
    question = screen == 'supplies' and not state['missing'] and not state['help_open']
    if question:
        # No / Yes are the big choice buttons in the body; Back sits in the footer like the other screens.
        # Knob order stays Back, No, Yes, so the first press lands on Yes.
        buttons.append(dict(action='back', label='Back', x=PAD_X, y=FOOTER_Y, width=104, height=48, primary=False))
        half = (WIDTH - 2 * PAD_X - 10) // 2
        for index, (action, label) in enumerate(actions):
            buttons.append(dict(action=action, label=label, x=PAD_X + index * (half + 10), y=112, width=half,
                                height=60, primary=False, choice=True))
        actions = []
    elif not state['help_open'] and screen == 'check' and state['simulated']:
        buttons.append(dict(action='back', label='Back', x=HELP_X - 8 - 84, y=6, width=84, height=44, primary=False))
    if len(actions) == 2:
        (left, left_label), (right, right_label) = actions
        buttons.append(dict(action=left, label=left_label, x=PAD_X, y=FOOTER_Y, width=128, height=48,
                            primary=left not in SECONDARY))
        buttons.append(dict(action=right, label=right_label, x=PAD_X + 128 + 8, y=FOOTER_Y,
                            width=WIDTH - 2 * PAD_X - 136, height=48, primary=right not in SECONDARY))
    elif actions:
        (action, label), = actions
        buttons.append(dict(action=action, label=label, x=WIDTH - PAD_X - 200, y=FOOTER_Y, width=200, height=48,
                            primary=True))
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
    image = Image.new('RGB', (WIDTH, HEIGHT), SURFACE)
    draw = ImageDraw.Draw(image)
    screen, protocol = state['screen'], state['protocol']

    def wrap(text, face, width):
        rows, line = [], ''
        for word in text.replace('\n', ' \n ').split(' '):
            if word == '\n':
                rows.append(line); line = ''; continue
            candidate = (line + ' ' + word).strip()
            if draw.textlength(candidate, font=face) > width and line:
                rows.append(line); line = word
            else:
                line = candidate
        if line:
            rows.append(line)
        return rows

    def lines(text, x, y, size=17, color=INK_SOFT, bold=False, width=WIDTH - 2 * PAD_X, max_lines=4,
              bottom=FOOTER_Y - 6, spacing=None, min_size=15):
        """Wrap text above `bottom`; shrink down to min_size before cutting with …. Returns the next free y."""
        while True:
            face = font(size, bold)
            step = spacing or round(size * 1.3)
            fits = max(1, min(max_lines, (bottom - y) // step))
            rows = wrap(text, face, width)
            if len(rows) <= fits or size <= min_size:
                break
            size, spacing = size - 1, spacing and spacing - 1
        max_lines = fits
        if len(rows) > max_lines:
            rows = rows[:max_lines]
            while rows[-1] and draw.textlength(rows[-1] + '…', font=face) > width:
                rows[-1] = rows[-1][:-1]
            rows[-1] += '…'
        for index, row in enumerate(rows):
            draw.text((x, y + index * step), row, font=face, fill=color)
        return y + len(rows) * step

    def title(text, y=58, size=22, max_lines=2):
        return lines(text, PAD_X, y, size=size, color=INK, bold=True, max_lines=max_lines, spacing=round(size * 1.25))

    # Header: brand or "Step X of N", segmented progress, then Back / Help pills on the right.
    total = len(protocol['prep_steps']) + 2
    step = 0 if screen == 'start' else 1 if screen == 'supplies' else state['prep_index'] + 2 if screen == 'prep' else total
    if not state['help_open']:
        if step:
            draw.text((PAD_X, 8), f'Step {step} of {total}', font=font(15, 'semibold'), fill=INK_SOFT)
        else:
            draw.text((PAD_X, 12), 'MedLock', font=font(18, True), fill=INK)
        right = min(b['x'] for b in state['buttons'] if b['y'] < 50) - 10
        if step:
            gap = 3
            seg = (right - PAD_X - gap * (total - 1)) / total
            for index in range(total):
                x = PAD_X + index * (seg + gap)
                draw.rounded_rectangle((x, 31, x + seg, 36), radius=3, fill=ACCENT if index < step else LINE)

    if state['help_open']:
        y = title(state['title'], y=12)
        lines(state['detail'], PAD_X, y + 6, max_lines=4)
    elif screen == 'supplies' and not state['missing']:
        item = protocol['supplies'][state['supply_index']]
        draw.text((PAD_X, 54), f"Do you have this? · {state['supply_index'] + 1} of {len(protocol['supplies'])}",
                  font=font(15, 'semibold'), fill=ACCENT)
        lines(item['label'], PAD_X, 74, size=26, color=INK, bold=True, max_lines=1)
    elif screen == 'supplies':
        item = protocol['supplies'][state['supply_index']]
        y = title(f"Get the {item['label'].lower()}")
        lines("You need this to prepare the shot. Can't find it? Tap Help to contact your clinic.", PAD_X, y + 4)
    elif screen == 'prep':
        prep = protocol['prep_steps'][state['prep_index']]
        y = title(prep['title'])
        warning = prep.get('warning')
        y = lines(prep['detail'], PAD_X, y + 4, bottom=FOOTER_Y - (44 if warning else 6))
        if warning:
            face = font(17, True)
            top = min(y + 6, FOOTER_Y - 42)
            draw.rounded_rectangle((PAD_X, top, WIDTH - PAD_X, top + 34), radius=10, fill=TONES['fix'][1],
                                   outline=TONES['fix'][0], width=2)
            draw.text((PAD_X + 10, top + 17), warning, font=face, fill=TONES['fix'][0], anchor='lm')
    elif screen == 'result':
        result = state['result']
        tone = 'pass' if result['verdict'] == 'pass' else 'fix' if result['verdict'] == 'fix' else 'unable'
        color, background, symbol = TONES[tone]
        heading = state['title'][2:] if state['title'][:2] in {'✓ ', '! ', '? '} else state['title']
        draw.rounded_rectangle((PAD_X, 50, WIDTH - PAD_X, FOOTER_Y - 8), radius=RADIUS, fill=background,
                               outline=color, width=2)
        draw.ellipse((PAD_X + 10, 60, PAD_X + 54, 104), fill=color)
        draw.text((PAD_X + 32, 82), symbol, font=symbol_font(26) if symbol == '✓' else font(26, True),
                  fill='white', anchor='mm')
        hx = PAD_X + 64
        lines(heading, hx, 60, size=20, color=INK, bold=True, width=WIDTH - PAD_X - 10 - hx, max_lines=2,
              spacing=24, bottom=110)
        lines(state['detail'], PAD_X + 10, 112, size=16, color=color if tone == 'fix' else INK, bold=True,
              width=WIDTH - 2 * PAD_X - 20, max_lines=3, bottom=FOOTER_Y - 12, spacing=21)
    elif screen == 'checking':
        y = title('Checking your syringe…')
        draw.arc((PAD_X, y + 8, PAD_X + 40, y + 48), 0, 360, fill=LINE, width=5)
        draw.arc((PAD_X, y + 8, PAD_X + 40, y + 48), -90, 0, fill=ACCENT, width=5)
        lines(state['detail'], PAD_X + 54, y + 8, width=WIDTH - 2 * PAD_X - 54, max_lines=3, bottom=HEIGHT - 8)
    else:
        y = title(state['title'])
        lines(state['detail'], PAD_X, y + 4, bottom=FOOTER_Y - 24 if screen in {'start', 'check'} else FOOTER_Y - 6)
    if not state['help_open'] and screen in {'start', 'check', 'checking'}:
        draw.text((PAD_X, FOOTER_Y - 20), 'Photo replay · bench prototype' if state['simulated'] else 'Hardware · bench prototype',
                  font=font(13), fill=INK_SOFT)

    for button in state['buttons']:
        x, y, w, h = (button[key] for key in ('x', 'y', 'width', 'height'))
        primary = button.get('primary', button['action'] not in SECONDARY)
        pill = y < 50
        if primary:
            draw.rounded_rectangle((x, y + 3, x + w - 1, y + h + 1), radius=RADIUS, fill='#c9d4f2')  # soft shadow
        if button.get('choice'):
            draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=RADIUS, fill=SURFACE, outline=LINE, width=2)
            mark = '✓' if button['action'] == 'confirm' else '✕'
            label_face, mark_face = font(24, 'semibold'), symbol_font(24)
            total_w = draw.textlength(mark, font=mark_face) + 8 + draw.textlength(button['label'], font=label_face)
            left = x + (w - total_w) / 2
            draw.text((left, y + h / 2), mark, font=mark_face, fill=ACCENT, anchor='lm')
            draw.text((left + draw.textlength(mark, font=mark_face) + 8, y + h / 2), button['label'],
                      font=label_face, fill=INK, anchor='lm')
        else:
            draw.rounded_rectangle((x, y, x + w - 1, y + h - 1), radius=22 if pill else RADIUS,
                                   fill=ACCENT if primary else SURFACE_2)
            draw.text((x + w / 2, y + h / 2), button['label'], font=font(16 if pill else 18, 'semibold'),
                      fill='white' if primary else (INK_SOFT if pill else INK), anchor='mm')
        if state.get('focus_action') == button['action']:
            focus_ring(draw, button)
    return image
