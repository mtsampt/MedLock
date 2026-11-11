"""Mirror station frames through the Pi's existing, working medlock_home.py driver.

The startup file is read, never edited. Only its three display functions are
loaded; its top-level GPIO initialization and infinite loop are not executed.
Optional touch uses a configured Linux input device. No touch GPIO is guessed.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

FUNCTIONS = {'command', 'init_lcd', 'display_image'}
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def extract_functions(source):
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    if {n.name for n in functions} != FUNCTIONS:
        raise ValueError('Startup driver must define command, init_lcd and display_image.')
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in {'WIDTH','HEIGHT','DC_GPIO','BL_GPIO'}:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    expected = {'WIDTH':320,'HEIGHT':240,'DC_GPIO':22,'BL_GPIO':18}
    if constants != expected:
        raise ValueError(f'Driver constants differ from the recorded setup: {constants}. Recheck wiring first.')
    opens = [n for n in tree.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Attribute) and isinstance(n.value.func.value, ast.Name)
             and n.value.func.value.id=='spi' and n.value.func.attr=='open']
    if len(opens)!=1 or [ast.literal_eval(a) for a in opens[0].value.args] != [0,0]:
        raise ValueError('Expected the recorded SPI bus 0, device 0 setup.')
    return compile(ast.Module(body=functions,type_ignores=[]),'<existing display functions>','exec'), constants


def driver_pids(driver):
    result=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name)==os.getpid():
            continue
        try:
            argv=(entry/'cmdline').read_bytes().split(b'\0')
            if len(argv)>1 and Path(argv[1].decode()).resolve()==driver.resolve():
                result.append(int(entry.name))
        except (OSError,UnicodeError):
            continue
    return result


def alive(pid):
    try:
        os.kill(pid,0)
        return True
    except ProcessLookupError:
        return False


def stop_home(driver):
    stopped=False
    for pid in driver_pids(driver):
        print(f'Stopping only the existing home-screen process ({pid}).',flush=True)
        for sig,seconds in [(signal.SIGINT,3),(signal.SIGTERM,2)]:
            if not alive(pid):break
            os.kill(pid,sig)
            deadline=time.monotonic()+seconds
            while alive(pid) and time.monotonic()<deadline:time.sleep(.1)
        if alive(pid):
            raise RuntimeError('The home-screen process did not stop. No display takeover attempted.')
        stopped=True
    if driver_pids(driver):
        raise RuntimeError('The home screen automatically restarted. Identify its startup service before continuing.')
    return stopped


def read_frame(url):
    with urlopen(url,timeout=5) as response:
        data=response.read(1_000_001)
    if len(data)>1_000_000:raise ValueError('Frame response is too large.')
    with Image.open(io.BytesIO(data)) as source:
        if source.size!=(320,240):raise ValueError('Expected a 320 x 240 station frame.')
        return source.convert('RGB')


def read_state(url):
    with urlopen(url,timeout=5) as response:
        state=json.loads(response.read(1_000_000))
    if not isinstance(state,dict) or not isinstance(state.get('buttons'),list):
        raise ValueError('Expected MedLock touchscreen state.')
    return state


def forward_tap(url,state,x,y):
    if not isinstance(state.get('revision'),int):
        raise ValueError('Touch requires restarting the updated station backend. Stop and relaunch Step 6.')
    for button in state['buttons']:
        if button['x']<=x<button['x']+button['width'] and button['y']<=y<button['y']+button['height']:
            data=json.dumps({'action':button['action'],'expected_revision':state['revision']}).encode()
            try:
                with urlopen(Request(url,data=data,headers={'Content-Type':'application/json'}),timeout=5) as response:
                    response.read()
            except HTTPError as exc:
                if exc.code!=409:raise
            return True
    return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--driver',type=Path,default=Path('/home/medlock/medlock_home.py'))
    parser.add_argument('--start-app',action='store_true',help='Start the local camera app if it is not running')
    parser.add_argument('--take-over',action='store_true',help='Temporarily stop the exact home-screen script')
    parser.add_argument('--rotation',type=int,choices=[0,90,180,270],default=90)
    parser.add_argument('--replay',action='store_true',help='Use saved photos if this command starts the app')
    parser.add_argument('--touch-device',type=Path,help='Confirmed ADS7846/XPT2046 /dev/input/eventX')
    parser.add_argument('--touch-swap',action='store_true')
    parser.add_argument('--touch-invert-x',action='store_true')
    parser.add_argument('--touch-invert-y',action='store_true')
    args=parser.parse_args()
    if sys.platform!='linux':parser.error('Run this bridge on the Raspberry Pi, not the Mac.')
    code,constants=extract_functions(args.driver.read_text())
    frame_url='http://127.0.0.1:8767/api/touch/frame'
    state_url='http://127.0.0.1:8767/api/touch'
    # Verify dependencies before stopping the working display.
    import spidev
    from gpiozero import DigitalOutputDevice
    backend=None
    dc=backlight=spi=touch=None
    stopped=False
    try:
        try:
            first_frame=read_frame(frame_url)
        except (URLError,TimeoutError):
            if not args.start_app:raise RuntimeError('Start Step 4/5 first, or add --start-app.')
            command=[sys.executable,'-m','medlock_device','--bundle','outputs/pi-bundle',
                     '--rotation',str(args.rotation)]
            if args.replay:command += ['--replay','outputs/medlock-pilot-2026-10-21/images']
            backend=subprocess.Popen(command,cwd=ROOT,start_new_session=True)
            deadline=time.monotonic()+60
            while True:
                if backend.poll() is not None:raise RuntimeError('Station app failed to start; see its error above.')
                try:
                    first_frame=read_frame(frame_url);break
                except (URLError,TimeoutError):
                    if time.monotonic()>deadline:raise RuntimeError('Station app startup timed out.')
                    time.sleep(.3)
        if args.touch_device:
            # Require the new revision guard before touching the running display.
            state=read_state(state_url)
            if not isinstance(state.get('revision'),int):
                raise ValueError('Restart the updated station backend before enabling touch.')
            from medlock_device.display_hardware import EvdevTouch
            touch=EvdevTouch(args.touch_device,args.touch_swap,args.touch_invert_x,args.touch_invert_y,exclusive=True)
        if driver_pids(args.driver):
            if not args.take_over:raise RuntimeError('Home screen is running. Add --take-over to temporarily replace it.')
            stopped=stop_home(args.driver)
        dc=DigitalOutputDevice(22,initial_value=False)
        backlight=DigitalOutputDevice(18,initial_value=True)
        spi=spidev.SpiDev();spi.open(0,0);spi.max_speed_hz=8_000_000;spi.mode=0
        namespace={'time':time,'spi':spi,'dc':dc,**constants}
        exec(code,namespace)
        namespace['init_lcd']()
        shown_state=None
        previous=None
        print('\nMedLock is now mirrored to the little screen.',flush=True)
        print('Touch enabled: '+str(args.touch_device) if touch else
              'Use the Pi browser at http://127.0.0.1:8767/ to operate it. Touch is not configured yet.',flush=True)
        print('Ctrl+C stops the bridge and restores the previous home-screen program.',flush=True)
        next_frame=0
        while True:
            if time.monotonic()>=next_frame:
                before=read_state(state_url)
                frame=read_frame(frame_url)
                after=read_state(state_url)
                # Only accept taps on a frame paired with stable button state.
                shown_state=before if before==after else None
                pixels=frame.tobytes()
                if pixels!=previous:
                    namespace['display_image'](frame)
                    previous=pixels
                next_frame=time.monotonic()+.3
            if touch:
                for x,y in touch.read_taps():
                    if shown_state is not None and forward_tap(state_url,shown_state,x,y):
                        shown_state=None
                        next_frame=0
                        break
            time.sleep(.03 if touch else .1)
    finally:
        if touch is not None:touch.close()
        if spi is not None:spi.close()
        if dc is not None:dc.close()
        if backlight is not None:backlight.close()
        if backend is not None and backend.poll() is None:
            backend.terminate()
            try:backend.wait(timeout=25)
            except subprocess.TimeoutExpired:
                print('Camera app still stopping; wait before starting another copy.',file=sys.stderr)
        if stopped and not driver_pids(args.driver):
            subprocess.Popen(['/usr/bin/python3',str(args.driver)],start_new_session=True,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            print('Original home-screen program restarted.',flush=True)


if __name__=='__main__':
    def stop(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:main()
    except KeyboardInterrupt:pass
    except Exception as exc:
        print(f'Display bridge stopped: {exc}',file=sys.stderr)
        sys.exit(1)
