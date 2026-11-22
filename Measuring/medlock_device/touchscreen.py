"""Shared 320 x 240 frame renderer and interaction model for browser and SPI."""
from __future__ import annotations

import threading
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

WIDTH, HEIGHT = 320, 240
# Same tokens as medlock-ui/src/styles.css, so the LCD matches the patient UI.
SURFACE, SURFACE_2, INK, INK_SOFT, LINE = '#ffffff', '#f2f4f8', '#1c2434', '#5b6678', '#dde2ea'
ACCENT = '#2f5bd3'
PASS, PASS_BG = '#2e7d4f', '#e6f3ec'
FIX, FIX_BG = '#b26a00', '#fdf1df'
UNABLE, UNABLE_BG = '#5a6472', '#eceef1'
RADIUS, PILL = 14, 22
PAD_X, FOOTER_Y = 10, HEIGHT-6-48
FONTS = Path(__file__).parent/'fonts'


@lru_cache(maxsize=32)
def font(size, bold=False):
    return ImageFont.truetype(str(FONTS/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),size)


def buttons(screen, seated, gpio=False):
    def button(action, label, x=110, width=200, y=FOOTER_Y, height=48, primary=True):
        return {'action':action,'label':label,'x':x,'y':y,'width':width,'height':height,'primary':primary}
    if screen=='checking':
        return []
    if screen=='help':
        return [button('close_help','Close')]
    help_button=button('help','? Help',x=WIDTH-PAD_X-90,width=90,y=6,height=44,primary=False)
    if screen=='ready':
        result=[button('capture','Check syringe')]
        if not gpio:
            result=[button('seat','Unseat (demo)' if seated else 'Seat (demo)',x=PAD_X,width=140,primary=False),
                    button('capture','Check syringe',x=158,width=152)]
        return [help_button]+result
    if screen=='details':
        return [help_button,button('back','Back to result')]
    return [help_button,button('details','Details',x=PAD_X,width=110,primary=False),
            button('retry','Check again',x=128,width=182)]


class TouchUI:
    def __init__(self, station):
        self.station=station
        self.screen='ready'
        self.help_return='ready'
        self.seated=False
        self.result={}
        self.revision=0
        self.lock=threading.RLock()

    def snapshot(self):
        with self.lock:
            gpio=self.station.seat is not None
            return {'screen':self.screen,'seated':self.seated,'gpio':gpio,
                    'revision':self.revision,
                    'step':1 if self.screen=='ready' or (self.screen=='help' and self.help_return=='ready') else 2,
                    'replay':self.station.camera.mode.startswith('photo replay'),
                    'buttons':buttons(self.screen,self.seated,gpio),
                    'result':dict(self.result)}

    def action(self, action, expected_revision=None):
        with self.lock:
            if expected_revision is not None and expected_revision!=self.revision:
                return False
            allowed={b['action'] for b in buttons(self.screen,self.seated,self.station.seat is not None)}
            if action not in allowed:
                return False
            if action=='help':
                self.help_return=self.screen
                self.screen='help'
            elif action=='close_help':
                self.screen=self.help_return
            elif action=='seat':
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
            self.revision+=1
            return True

    def _capture(self):
        try:
            result,_=self.station.check(self.seated)
        except Exception:
            result={'state':'unable','message':'Cannot save the result. Check device storage.'}
        with self.lock:
            self.result=result
            self.screen='result'
            self.revision+=1

    def render(self):
        return render(self.snapshot(), self.station.preview)


def render(state, preview=None):
    im=Image.new('RGB',(WIDTH,HEIGHT),SURFACE)
    d=ImageDraw.Draw(im)
    screen=state['screen']; result=state['result']
    step=state.get('step',1 if screen=='ready' else 2)

    def lines(text,x,y,size=17,color=INK_SOFT,width=WIDTH-2*PAD_X,max_lines=2,bold=False,spacing=None):
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
        step_y=spacing or round(size*1.3)
        for i,row in enumerate(rows):
            d.text((x,y+i*step_y),row,font=f,fill=color)
        return y+len(rows)*step_y

    def title(text,y=60):
        return lines(text,PAD_X,y,size=22,color=INK,bold=True,spacing=28)

    # Header: step label and segmented progress, Help pill on the right.
    if screen!='help':
        d.text((PAD_X,8),'Step %s of 2' % step,font=font(15,True),fill=INK_SOFT)
        right=WIDTH-PAD_X-90-10
        seg=(right-PAD_X-3)//2
        for i in range(2):
            x=PAD_X+i*(seg+3)
            d.rounded_rectangle((x,32,x+seg,37),radius=3,fill=ACCENT if i<step else LINE)

    if screen=='ready':
        y=title('Place the syringe\nin the dock')
        lines('Press it in until it clicks.' if not state['seated'] else 'Syringe is in the dock (demo).',
              PAD_X,y+4,max_lines=1)
        if state.get('replay'):
            lines('Prototype · saved photos',PAD_X,FOOTER_Y-20,size=13,max_lines=1)
    elif screen=='checking':
        y=title('Checking your\nsyringe…',y=66)
        d.arc((PAD_X,y+10,PAD_X+40,y+50),0,360,fill=LINE,width=5)
        d.arc((PAD_X,y+10,PAD_X+40,y+50),-90,0,fill=ACCENT,width=5)
        lines('Keep it still.',PAD_X+54,y+20,max_lines=1)
    elif screen=='help':
        y=title('Need help?',y=12)
        y=lines('Push the syringe fully into the dock, barrel facing the camera. Keep it still while it checks.',
                PAD_X,y+6,max_lines=4)
        lines('Air check only. Volume is not checked.',PAD_X,y+8,size=13,max_lines=1)
    elif screen=='details':
        d.rounded_rectangle((PAD_X,58,PAD_X+96,154),radius=10,fill=SURFACE_2,outline=LINE)
        if preview:
            crop=ImageOps.contain(preview,(90,90))
            im.paste(crop,(PAD_X+3+(90-crop.width)//2,61+(90-crop.height)//2))
        x=PAD_X+108
        lines('Check details',x,60,size=17,color=INK,bold=True,width=WIDTH-PAD_X-x,max_lines=1)
        lines(f"Model: {result.get('inference_ms','—')} ms\nTotal: {result.get('elapsed_ms','—')} ms\nVolume: not checked",
              x,88,size=15,width=WIDTH-PAD_X-x,max_lines=3,spacing=21)
        note=('Prototype result. Not clearance to inject.' if result.get('state') in {'air_detected','no_air_detected'}
              else result.get('message','No result available.'))
        lines(note,PAD_X,160,size=13,max_lines=1)
    else:
        status=result.get('state')
        color,background,symbol,heading,reason,action={
            'no_air_detected':(PASS,PASS_BG,'✓','No visible air','',
                               'Air check passed. Volume was not checked.'),
            'air_detected':(FIX,FIX_BG,'!','Needs a fix','Air bubble detected',
                            'Tap the syringe so the bubble rises, then push the air out.'),
        }.get(status,(UNABLE,UNABLE_BG,'?',"Couldn't check",result.get('message','Something went wrong.'),
                      'Make sure the syringe is fully in the dock, then check again.'))
        d.rounded_rectangle((PAD_X,56,WIDTH-PAD_X,FOOTER_Y-8),radius=RADIUS,fill=background,outline=color,width=2)
        d.ellipse((PAD_X+10,66,PAD_X+54,110),fill=color)
        d.text((PAD_X+32,88),symbol,font=font(26,True),fill='white',anchor='mm')
        hx=PAD_X+64; hw=WIDTH-PAD_X-10-hx
        if reason:
            lines(heading,hx,66,size=20,color=INK,bold=True,width=hw,max_lines=1)
            lines(reason,hx,90,size=16,color=FIX if status=='air_detected' else INK,bold=True,width=hw,max_lines=1)
        else:
            lines(heading,hx,77,size=20,color=INK,bold=True,width=hw,max_lines=1)
        lines(action,PAD_X+10,118,size=15,color=INK,width=WIDTH-2*PAD_X-20,max_lines=2,spacing=20)

    for b in state['buttons']:
        x,y,w,h=b['x'],b['y'],b['width'],b['height']
        primary=b.get('primary',b['action'] in {'capture','retry','back','close_help'})
        is_help=b['action']=='help'
        if primary:
            d.rounded_rectangle((x,y+3,x+w-1,y+h+1),radius=RADIUS,fill='#c9d4f2')  # soft shadow
        d.rounded_rectangle((x,y,x+w-1,y+h-1),radius=PILL if is_help else RADIUS,
                            fill=ACCENT if primary else SURFACE_2)
        d.text((x+w/2,y+h/2),b['label'],font=font(16,True),
               fill='white' if primary else (INK_SOFT if is_help else INK),anchor='mm')
    return im
