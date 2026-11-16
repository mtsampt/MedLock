"""Original Measuring touchscreen presentation, backed by the guided session."""
from PIL import Image, ImageDraw, ImageOps

from .touchscreen import font, WIDTH, HEIGHT

NAVY, TEAL, PAPER, MUTED = '#20272b', '#2b567c', '#fdfdfd', '#626b70'


def snapshot(session, details=False):
    state = session.snapshot()
    screen = 'help' if state['help_open'] else {'check': 'ready'}.get(state['screen'], state['screen'])
    if details and screen == 'result':
        screen = 'details'
    result = dict(state['result'] or {})
    # Preserve controller failures even if air inference succeeded earlier.
    if result.get('verdict') == 'unable' and result.get('reason_code') != 'volume_unverified':
        result['state'] = 'unable'
    buttons = [dict(action='guided', label='Back', x=12, y=6, width=68, height=44)]
    def button(action, label, x=12, width=296):
        return dict(action=action, label=label, x=x, y=180, width=width, height=48)
    if screen != 'help':
        buttons.append(dict(action='help', label='? Help', x=248, y=6, width=60, height=44))
    if screen == 'ready':
        if state['simulated']:
            buttons.append(button('seat', 'Unseat (demo)' if state['seated'] else 'Seat (demo)', width=144))
        buttons.append(button('capture', 'Check syringe', x=164 if state['simulated'] else 12, width=144 if state['simulated'] else 296))
    elif screen == 'result':
        buttons.extend([button('retry', 'Check again', width=144), button('details', 'Details', x=164, width=144)])
    elif screen == 'details':
        buttons.append(button('back_to_result', 'Back to result'))
    elif screen == 'help':
        buttons.append(button('close_help', 'Back'))
    return dict(state, screen=screen, result=result, buttons=buttons,
                gpio=state['hardware_seat'], replay=state['simulated'], guided_screen=state['screen'])


def render(state, preview=None):
    im=Image.new('RGB',(WIDTH,HEIGHT),PAPER)
    d=ImageDraw.Draw(im)
    screen=state['screen']; result=state['result']

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

    if screen=='ready':
        lines('Check your syringe',12,57,size=20,bold=True)
        d.rounded_rectangle((12,89,100,159),radius=5,fill='#f1f3f4',outline='#d6dbde')
        # Native line illustration: barrel, stopper, plunger and tip.
        d.rounded_rectangle((31,117,77,134),radius=2,outline='#73828b',width=2,fill='#e4edf1')
        d.line((28,113,28,138),fill=TEAL,width=2)
        d.line((18,125,39,125),fill=TEAL,width=2)
        d.line((18,119,18,131),fill=TEAL,width=2)
        d.rectangle((38,118,42,133),fill=TEAL)
        d.line((77,125,91,125),fill='#73828b',width=2)
        for x in [49,56,63,70]:d.line((x,118,x,122),fill='#73828b')
        lines('Place syringe in dock.\nKeep the barrel visible.\nHold still.',110,92,size=12,width=198,max_lines=3)
        seat_text=('Seated (demo)' if state['seated'] else 'Tap Seat to simulate') if not state['gpio'] else 'Seat sensor on capture'
        lines(seat_text,110,146,size=10,color=MUTED,width=198,max_lines=1)
    elif screen=='checking':
        lines('Checking your syringe…',12,65,size=20,bold=True)
        d.arc((14,108,44,138),0,290,fill=TEAL,width=3)
        lines('Keep the syringe still.\nThis may take a few seconds.',54,108,size=13,width=252,max_lines=2)
    elif screen=='help':
        lines('Camera check help',12,58,size=20,bold=True)
        lines('Seat the syringe with the full barrel visible. Keep it still and use even lighting.',12,93,size=14,max_lines=3)
        lines('Air check only. Volume not checked.',12,155,size=11,color=MUTED,max_lines=1)
    elif screen=='details':
        d.rounded_rectangle((12,61,108,153),radius=5,fill='#f1f3f4',outline='#d6dbde')
        if preview:
            crop=ImageOps.contain(preview,(90,86))
            im.paste(crop,(15+(90-crop.width)//2,64+(86-crop.height)//2))
        lines('Camera check details',118,62,size=13,bold=True,width=190,max_lines=1)
        volume = 'not checked' if result.get('volume_ml') is None else f"{result['volume_ml']:.2f} mL"
        lines(f"Inference: {result.get('inference_ms','—')} ms\nTotal: {result.get('elapsed_ms','—')} ms\nVolume: {volume}",118,88,size=12,width=190,max_lines=3)
        if result.get('state') in {'air_detected','no_air_detected'}:
            note='Experimental result. Not injection clearance.'
        else:
            note=result.get('message','No result available.')
        lines(note,12,155,size=10,color=MUTED,max_lines=1)
    else:
        title,color,background,description={
            'air_detected':('Air detected','#a56b14','#fff3df','Visible air flagged.\nCorrect and recheck.'),
            'no_air_detected':('No visible air','#2c774c','#e0f0e8','Volume not checked.\nNot injection clearance.'),
        }.get(result.get('state'),('Unable to verify','#a56b14','#fff3df','Check seating and focus.\nThen capture again.'))
        d.rounded_rectangle((12,65,308,148),radius=5,fill=background,outline=color,width=1)
        d.ellipse((23,87,57,121),fill=color)
        d.text((40,103),'i' if result.get('state')=='no_air_detected' else '!',font=font(22,True),fill='white',anchor='mm')
        lines(title,67,77,size=18,bold=True,width=230,max_lines=1)
        lines(description,67,106,size=11,width=230,max_lines=2)
        lines('Camera check only · volume not verified',12,155,size=10,color=MUTED,max_lines=1)
    if screen!='help':
        mode='Photo replay · prototype' if state['replay'] else ('Seat input simulated' if not state['gpio'] else 'Prototype camera check')
        if screen in {'ready','checking'}:lines(mode,12,164,size=10,color=MUTED,max_lines=1)
    for b in state['buttons']:
        x,y,w,h=b['x'],b['y'],b['width'],b['height']
        secondary=b['action'] in {'guided','help','seat','retry','back_to_result','close_help'}
        fill=PAPER if secondary else TEAL
        d.rounded_rectangle((x,y,x+w-1,y+h-1),radius=5,fill=fill,outline='#cbd0d3' if secondary else TEAL,width=1)
        d.text((x+w/2,y+h/2),b['label'],font=font(12 if b['action'] in {'guided', 'help'} else 14,True),fill=NAVY if secondary else 'white',anchor='mm')
    return im
