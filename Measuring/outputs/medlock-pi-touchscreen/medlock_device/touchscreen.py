"""Shared 320 x 240 frame renderer and interaction model for browser and SPI."""
from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 320, 240
NAVY, TEAL, PAPER, MUTED = '#1b2a41', '#0f7c8c', '#ffffff', '#58687a'
FONTS = Path(__file__).parent/'fonts'


@lru_cache(maxsize=32)
def font(size, bold=False):
    return ImageFont.truetype(str(FONTS/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),size)


def buttons(screen, seated, gpio=False):
    def button(action, label, x=12, width=296, y=180):
        return {'action':action,'label':label,'x':x,'y':y,'width':width,'height':48}
    if screen=='checking':
        return []
    if screen=='ready':
        result=[button('capture','Check syringe')]
        if not gpio:
            result.insert(0,button('seat','Unseat (simulated)' if seated else 'Seat (simulated)',y=118))
        return result
    if screen=='details':
        return [button('back','Back to result')]
    return [button('retry','Check again',width=144),button('details','Details',x=164,width=144)]


class TouchUI:
    def __init__(self, station):
        self.station=station
        self.screen='ready'
        self.seated=False
        self.result={}
        self.lock=threading.RLock()

    def snapshot(self):
        with self.lock:
            gpio=self.station.seat is not None
            return {'screen':self.screen,'seated':self.seated,'gpio':gpio,
                    'replay':self.station.camera.mode.startswith('photo replay'),
                    'buttons':buttons(self.screen,self.seated,gpio),
                    'result':dict(self.result)}

    def action(self, action):
        with self.lock:
            allowed={b['action'] for b in buttons(self.screen,self.seated,self.station.seat is not None)}
            if action not in allowed:
                return False
            if action=='seat':
                self.seated=not self.seated
            elif action=='capture':
                self.screen='checking'
                self.result={}
                threading.Thread(target=self._capture,daemon=True).start()
            elif action=='retry':
                self.screen='ready'
                self.seated=False
                self.result={}
            elif action=='details':
                self.screen='details'
            elif action=='back':
                self.screen='result'
            return True

    def _capture(self):
        try:
            result,_=self.station.check(self.seated)
        except Exception:
            result={'state':'unable','message':'Cannot save the result. Check device storage.'}
        with self.lock:
            self.result=result
            self.screen='result'

    def render(self):
        return render(self.snapshot(), self.station.preview)


def render(state, preview=None):
    im=Image.new('RGB',(WIDTH,HEIGHT),PAPER)
    d=ImageDraw.Draw(im)
    d.rectangle((0,0,319,27),fill=NAVY)
    d.text((12,5),'MEDLOCK',font=font(15,True),fill='white')
    mode='PHOTO REPLAY' if state['replay'] else ('CAMERA / GPIO' if state['gpio'] else 'SEAT SIMULATION')
    d.text((308,8),mode,font=font(10),fill='#a8e4e9',anchor='ra')

    def lines(text,x,y,size=15,color=NAVY,width=296,max_lines=3,bold=False):
        f=font(size,bold)
        words=text.replace('\n',' \n ').split(' ')
        rows=[]; line=''
        for word in words:
            if word=='\n':
                rows.append(line);line='';continue
            candidate=(line+' '+word).strip()
            if d.textlength(candidate,font=f)>width and line:
                rows.append(line);line=word
            else:
                line=candidate
        if line:rows.append(line)
        if len(rows)>max_lines:
            rows=rows[:max_lines]
            while d.textlength(rows[-1]+'…',font=f)>width:rows[-1]=rows[-1][:-1]
            rows[-1]+='…'
        for i,row in enumerate(rows):
            d.text((x,y+i*(size+5)),row,font=f,fill=color)

    screen=state['screen']; result=state['result']
    if screen=='ready':
        lines('Place syringe in dock',12,40,size=21,bold=True)
        lines('Keep the full barrel visible.\nHold the syringe still.',12,77,size=15,max_lines=2)
        if state['gpio']:
            lines('Seat sensor checked on capture',12,133,size=14,color=TEAL)
        else:
            # The button explicitly marks the seat input as simulation.
            lines('Seated' if state['seated'] else 'Not seated',12,166,size=10,color=MUTED)
    elif screen=='checking':
        lines('Checking syringe…',12,50,size=23,bold=True)
        lines('Hold still while the camera\ncaptures and checks the image.',12,95,size=16,max_lines=2)
        d.rounded_rectangle((12,160,308,168),radius=4,fill='#dfecef')
        d.rounded_rectangle((12,160,130,168),radius=4,fill=TEAL)
        lines('Please wait',12,190,size=16,color=MUTED)
    elif screen=='details':
        if preview:
            im.paste(ImageOps.contain(preview,(96,96)),(12,40))
        else:
            d.rectangle((12,40,108,136),fill='#edf2f3')
        lines('Camera check only',120,40,size=14,bold=True,width=188,max_lines=1)
        lines(f"Inference: {result.get('inference_ms','—')} ms\nTotal: {result.get('elapsed_ms','—')} ms\nVolume: not checked",120,66,size=12,width=188,max_lines=3)
        if result.get('state') in {'air_detected','no_air_detected'}:
            note='Experimental air result. Not injection clearance.'
        else:
            note=result.get('message','No result available.')
        lines(note,12,142,size=12,color=MUTED,max_lines=2)
    else:
        status=result.get('state')
        title,color,description={
            'air_detected':('AIR DETECTED','#a54410','Visible air flagged.\nCorrect preparation and recheck.'),
            'no_air_detected':('NO AIR DETECTED',TEAL,'Camera check only.\nNot injection clearance.'),
        }.get(status,('UNABLE TO VERIFY','#ad2929','Check seating, framing and focus.\nThen capture again.'))
        lines(title,12,43,size=22,bold=True,color=color)
        d.rectangle((12,77,308,81),fill=color)
        lines(description,12,94,size=15,max_lines=2)
        lines('Volume not checked · Prototype',12,151,size=12,color=MUTED,max_lines=1)
    for b in state['buttons']:
        x,y,w,h=b['x'],b['y'],b['width'],b['height']
        fill=TEAL if b['action'] not in {'details','seat'} else NAVY
        d.rounded_rectangle((x,y,x+w-1,y+h-1),radius=7,fill=fill)
        d.text((x+w/2,y+h/2),b['label'],font=font(15,True),fill='white',anchor='mm')
    return im
