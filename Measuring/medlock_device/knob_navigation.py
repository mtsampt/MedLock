"""Visible button focus for the LCD bridge; GPIO events come from knob.py."""
import importlib.util
import queue
from pathlib import Path

from PIL import ImageDraw

_VISIBLE = object()


def load_knob():
    path = Path(__file__).resolve().parents[2]/'medlock-ui/pi/knob.py'
    spec = importlib.util.spec_from_file_location('medlock_shared_knob',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KnobNavigation:
    def __init__(self):
        self.events = queue.Queue(maxsize=64)
        self.state = None
        self.selected = None
        self.devices = ()
        self.received = 0

    def attach(self,a=5,b=6,button=13,reverse=False,button_active_high=False):
        if any(pin in {7,8,9,10,11,18,22} for pin in (a,b,button)):
            raise ValueError('Knob GPIO conflicts with the bridge display or SPI pins.')
        self.devices = load_knob().attach_controls(self.emit,a,b,button,reverse,button_active_high)

    def emit(self,action):
        # Capture the visible revision when GPIO fires; no HTTP in callbacks.
        self.received += 1
        state = self.state
        if state is not None:
            try:self.events.put_nowait((action,state['revision']))
            except queue.Full:pass

    def sync(self,state):
        self.state = state
        buttons = [] if state is None else state['buttons']
        if self.selected not in {b['action'] for b in buttons}:
            default = next((b for b in buttons if b['action']!='help'),None)
            self.selected = (default or (buttons[0] if buttons else {})).get('action')

    def read(self):
        """Apply queued rotation; return selected button + revision on press."""
        while True:
            try:action,revision = self.events.get_nowait()
            except queue.Empty:return None
            state = self.state
            if state is None or revision!=state['revision'] or not state['buttons']:
                continue
            buttons = state['buttons']
            index = next((i for i,b in enumerate(buttons) if b['action']==self.selected),0)
            if action in ('next','prev'):
                self.selected = buttons[(index+(1 if action=='next' else -1))%len(buttons)]['action']
            elif action=='press':
                return state,buttons[index]

    def draw(self,frame,state=_VISIBLE):
        if state is _VISIBLE:state=self.state
        image = frame.copy()
        if state is not None:
            actions={b['action'] for b in state['buttons']}
            default=next((b for b in state['buttons'] if b['action']!='help'),None)
            default=default or (state['buttons'][0] if state['buttons'] else {})
            selected=self.selected if self.selected in actions else default.get('action')
            for button in state['buttons']:
                if button['action']==selected:
                    # Same ring as the patient UI: inset, white on the blue primary button.
                    x,y,w,h = (button[k] for k in ('x','y','width','height'))
                    radius = 16 if button['action']=='help' else 9
                    colour = '#ffffff' if button.get('primary') else '#1c2434'
                    ImageDraw.Draw(image).rounded_rectangle((x+5,y+5,x+w-6,y+h-6),radius=radius,outline=colour,width=3)
        return image

    def status(self):
        """Observe already-owned pins; no extra GPIO devices or pin scanning."""
        if not self.devices:return {'events':self.received,'levels':None}
        encoder=self.devices[0]
        levels={'A':int(encoder.a.pin.state),'B':int(encoder.b.pin.state)}
        if len(self.devices)>1:levels['SW']=int(self.devices[1].pin.state)
        return {'events':self.received,'levels':levels}

    def close(self):
        self.state = None
        for device in self.devices:device.close()
        self.devices = ()
