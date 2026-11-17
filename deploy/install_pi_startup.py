"""Install or remove automatic boot of the existing MedLock screen demo."""
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
MEASURING = REPO / 'Measuring'
UNIT = 'medlock-screen.service'
UNIT_PATH = Path('/etc/systemd/system') / UNIT
STATE = MEASURING / 'runtime' / 'pi-startup-backup.json'
DRIVER = Path('/home/medlock/medlock_home.py')


def run(*args, check=True, **kwargs):
    return subprocess.run(list(map(str, args)), check=check, text=True,
                          capture_output=True, **kwargs)


def ctl(scope, *args, check=True):
    prefix = ['sudo', 'systemctl'] if scope == 'system' else ['systemctl', '--user']
    return run(*prefix, *args, check=check)


def quote(value, exec_arg=False):
    value = str(value)
    if '\n' in value or '\r' in value:
        raise ValueError('Paths must not contain line breaks.')
    value = value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    if exec_arg:
        value = value.replace('$', '$$')
    return '"' + value + '"'


def service_text():
    values = {'MEASURING': quote(MEASURING), 'PYTHON': quote(MEASURING / '.venv/bin/python', exec_arg=True),
              'BRIDGE': quote(MEASURING / 'scripts/mirror_pi_display.py', exec_arg=True),
              'DRIVER': quote(DRIVER, exec_arg=True), 'USER': pwd.getpwuid(os.getuid()).pw_name,
              'GROUP': grp.getgrgid(os.getgid()).gr_name}
    text = (REPO / 'deploy/medlock-screen.service.in').read_text()
    for key, value in values.items():
        text = text.replace('@' + key + '@', value)
    return text


def home_services(scope):
    result = ctl(scope, 'list-unit-files', '--type=service', '--no-legend', '--no-pager', check=False)
    if result.returncode:
        return []
    names = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    if not names:
        return []
    details = ctl(scope, 'show', '--property=Id', '--property=ExecStart', *names, check=False)
    found = []
    # Match the exact script argument, never another service with a similar name.
    pattern = re.compile(r'(?<![\w/.-])' + re.escape(str(DRIVER)) + r'(?![\w/.-])')
    for block in details.stdout.split('\n\n'):
        fields = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
        name = fields.get('Id')
        if name and name != UNIT and pattern.search(fields.get('ExecStart', '')):
            found.append({'scope': scope, 'name': name,
                          'enabled': ctl(scope, 'is-enabled', name, check=False).stdout.strip() in {'enabled', 'enabled-runtime'},
                          'active': ctl(scope, 'is-active', name, check=False).returncode == 0})
    return found


def check_other_launchers():
    """Leave unrelated shell/desktop configuration alone; identify conflicts."""
    candidates = [Path('/etc/rc.local'), Path('/etc/crontab'),
                  *Path('/etc/cron.d').glob('*'),
                  *Path('/etc/xdg/autostart').glob('*.desktop'),
                  *Path.home().joinpath('.config/autostart').glob('*.desktop'),
                  *[Path.home() / name for name in ('.profile', '.bash_profile', '.bashrc')]]
    conflicts = []
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(errors='replace')
        if path.suffix == '.desktop' and re.search(r'^Hidden\s*=\s*true\s*$', text, re.M | re.I):
            continue
        if any(str(DRIVER) in line for line in text.splitlines() if not line.lstrip().startswith('#')):
            conflicts.append(str(path))
    if shutil.which('crontab'):
        cron = run('crontab', '-l', check=False)
        if any(str(DRIVER) in line for line in cron.stdout.splitlines() if not line.lstrip().startswith('#')):
            conflicts.append('your crontab (crontab -e)')
    if conflicts:
        raise RuntimeError('The old home screen also starts from: ' + ', '.join(conflicts)
                           + '. Remove its startup entry there, leaving medlock_home.py itself intact, then rerun this installer.')


def write_unit(text):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.service') as stream:
        stream.write(text)
        stream.flush()
        run('sudo', 'install', '-m', '0644', stream.name, UNIT_PATH)


def restore(backup):
    ctl('system', 'disable', '--now', UNIT, check=False)
    if backup['unit'] is None:
        run('sudo', 'rm', '-f', UNIT_PATH)
    else:
        write_unit(backup['unit'])
    ctl('system', 'daemon-reload')
    if backup.get('unit_enabled'):
        ctl('system', 'enable', UNIT)
    if backup.get('unit_active'):
        ctl('system', 'start', UNIT)
    for service in backup['services']:
        if service['enabled']:
            ctl(service['scope'], 'enable', service['name'])
        if service['active']:
            ctl(service['scope'], 'start', service['name'])


def install():
    python = MEASURING / '.venv/bin/python'
    if not python.is_file() or not os.access(python, os.X_OK):
        raise RuntimeError(f'Missing Pi virtual environment: {python}')
    if not DRIVER.is_file():
        raise RuntimeError(f'Missing existing display driver: {DRIVER}')
    print('Checking device dependencies and model files…', flush=True)
    run(python, '-m', 'pip', 'install', '-r', MEASURING / 'requirements-device.txt')
    run(python, '-c', 'import cv2, numpy, PIL, flask, waitress, gpiozero, spidev; '
        'from medlock_device.runtime import Engine; '
        'Engine("outputs/pi-bundle")', cwd=MEASURING)
    check_other_launchers()
    run('sudo', '-v')
    # Reject an independently running backend rather than attaching boot service
    # ownership to a process that will disappear when its terminal closes.
    running = ctl('system', 'is-active', UNIT, check=False).returncode == 0
    with socket.socket() as connection:
        connection.settimeout(1)
        occupied = connection.connect_ex(('127.0.0.1', 8767)) == 0
    if occupied and not running:
        raise RuntimeError('Stop the earlier screen bridge and measuring backend with Ctrl+C, then rerun this installer.')
    services = home_services('system') + home_services('user')
    backup = json.loads(STATE.read_text()) if STATE.exists() else {
        'unit': UNIT_PATH.read_text() if UNIT_PATH.exists() else None,
        'unit_enabled': ctl('system', 'is-enabled', UNIT, check=False).stdout.strip() == 'enabled',
        'unit_active': running, 'services': []}
    known = {(s['scope'], s['name']) for s in backup['services']}
    backup['services'].extend(s for s in services if (s['scope'], s['name']) not in known)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(backup, indent=2) + '\n')
    try:
        for service in services:
            print('Pausing old home screen: ' + service['name'], flush=True)
            ctl(service['scope'], 'disable', '--now', service['name'])
        ctl('system', 'stop', UNIT, check=False)
        write_unit(service_text())
        ctl('system', 'daemon-reload')
        ctl('system', 'enable', UNIT)
        print('Starting the screen service; waiting for its first frame…', flush=True)
        # Type=notify waits for the display's first frame, not just Python launch.
        ctl('system', 'start', UNIT)
    except Exception:
        print(ctl('system', 'status', UNIT, '--no-pager', check=False).stdout, file=sys.stderr)
        print(run('sudo', 'journalctl', '-u', UNIT, '-n', '40', '--no-pager', check=False).stdout, file=sys.stderr)
        restore(backup)
        raise
    print('Installed: combined flow is on the screen and enabled for every boot.\n'
          'Mode: saved photos, real model, existing screen and knob.\n'
          'Check logs: journalctl -u medlock-screen -b\n'
          'Undo: python3 deploy/install_pi_startup.py --uninstall')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true', help='Restore the earlier home-screen services')
    args = parser.parse_args()
    if sys.platform != 'linux' or not Path('/run/systemd/system').exists():
        parser.exit(1, 'Run this installer on the Raspberry Pi.\n')
    if os.getuid() == 0:
        parser.exit(1, 'Run as the normal medlock user, without sudo; the installer requests sudo when needed.\n')
    try:
        if args.uninstall:
            if not STATE.exists():
                raise RuntimeError('No startup installation backup was found.')
            run('sudo', '-v')
            restore(json.loads(STATE.read_text()))
            STATE.unlink()
            print('Automatic combined startup removed; earlier home-screen services restored.')
        else:
            install()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, 'stderr', None) or str(exc)
        parser.exit(1, detail.rstrip() + '\n')


if __name__ == '__main__':
    main()
