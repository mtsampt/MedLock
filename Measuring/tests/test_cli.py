import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import json

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('args, message', [([], 'requires --seat-pin'),(['--seat-pin','-1'],'BCM'),(['--replay','unused','--seat-pin','1'],'does not use GPIO'),(['--replay','unused','--display','ili9341'],'Native display needs')])
def test_cli_rejects_incomplete_hardware(args,message):
    result=subprocess.run([sys.executable,'-m','medlock_device',*args],cwd=ROOT,capture_output=True,text=True,timeout=10)
    assert result.returncode!=0 and message in result.stderr


def test_replay_server_sigterm_and_restart(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    command=[sys.executable,'-m','medlock_device','--replay',str(ROOT/'outputs/medlock-pilot-2026-10-21/images'),'--port',str(port),'--log',str(tmp_path/'events.jsonl')]
    ids=[]
    for _ in range(2):
        process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            deadline=time.monotonic()+10
            while True:
                assert process.poll() is None, process.stdout.read()
                try:
                    with urlopen(f'http://127.0.0.1:{port}/api/state',timeout=1) as response:
                        state=json.load(response)
                    break
                except OSError:
                    if time.monotonic()>deadline: pytest.fail('Server startup timed out')
                    time.sleep(.05)
            assert state['screen']=='start' and state['result'] is None
            ids.append(state['session_id'])
            process.send_signal(signal.SIGTERM)
            output,_=process.communicate(timeout=10)
            assert process.returncode==0,output
            assert 'Exception in thread' not in output and 'Traceback' not in output,output
        finally:
            if process.poll() is None:
                process.kill();process.wait()
    assert ids[0]!=ids[1]


@pytest.mark.parametrize('args,message',[
    (['--hardware-profile','rev0','--seat-active','low'],'active HIGH'),
    (['--hardware-profile','rev0','--replay','unused'],'does not use GPIO'),
    (['--encoder-a','5'],'Encoder requires'),
    (['--seat-pin','17','--encoder-a','17','--encoder-b','6','--encoder-switch','13'],'distinct'),
])
def test_hardware_profile_and_encoder_pin_validation(args,message):
    result=subprocess.run([sys.executable,'-m','medlock_device',*args],cwd=ROOT,capture_output=True,text=True,timeout=10)
    assert result.returncode!=0 and message in result.stderr
