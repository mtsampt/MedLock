import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('display_bridge',Path(__file__).parents[1]/'scripts/mirror_pi_display.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)

SOURCE='''
WIDTH=320
HEIGHT=240
DC_GPIO=22
BL_GPIO=18
spi.open(0,0)
def command(value,data=None):
    dc.append((value,data))
def init_lcd():
    command(1)
def display_image(image):
    command(44,[image])
raise RuntimeError('Top-level startup and loop must not run')
'''


def test_load_only_the_three_display_functions():
    code,constants=bridge.extract_functions(SOURCE)
    ns={'dc':[],**constants}
    exec(code,ns)
    ns['init_lcd']();ns['display_image']('frame')
    assert ns['dc']==[(1,None),(44,['frame'])]


def test_reject_other_wiring_or_incomplete_driver():
    for source in [SOURCE.replace('DC_GPIO=22','DC_GPIO=23'),SOURCE.replace('spi.open(0,0)','spi.open(0,1)'),SOURCE.replace('def init_lcd():','def other_init():')]:
        with pytest.raises(ValueError):bridge.extract_functions(source)
