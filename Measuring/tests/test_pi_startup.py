import importlib.util
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def installer():
    spec = importlib.util.spec_from_file_location('pi_startup', Path(__file__).parents[2] / 'deploy/install_pi_startup.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result(stdout='', code=0):
    return SimpleNamespace(stdout=stdout, stderr='', returncode=code)


def test_boot_unit_uses_existing_driver_and_waits_for_first_frame(installer):
    text = installer.service_text()
    assert '@MEASURING@' not in text
    for setting in ['Type=notify', 'NotifyAccess=main', 'KillMode=mixed',
                    'Restart=always', 'WantedBy=multi-user.target',
                    '--start-app --take-over --replay --service-mode']:
        assert setting in text
    assert 'medlock_home.py' in text
    assert 'ProtectHome=true' not in text
    assert 'network-online.target' not in text


def test_working_directory_is_an_unquoted_absolute_path(installer, monkeypatch):
    measuring = Path('/home/medlock/MedLock/Measuring')
    monkeypatch.setattr(installer, 'MEASURING', measuring)
    text = installer.service_text()
    directory = next(line.split('=', 1)[1] for line in text.splitlines() if line.startswith('WorkingDirectory='))
    assert directory == str(measuring)
    assert Path(directory).is_absolute()
    # Command arguments still need their own quoting rules.
    assert f'ExecStart="{measuring}/.venv/bin/python" ' in text


def test_validation_uses_the_pi_systemd_parser(installer, monkeypatch):
    calls = []
    def run(*args, **kwargs):
        assert args[:2] == ('systemd-analyze', 'verify')
        path = args[2]
        assert path.name == installer.UNIT
        calls.append(path.read_text())
        raise subprocess.CalledProcessError(1, list(args), stderr='bad unit setting')
    monkeypatch.setattr(installer, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        installer.validate_unit('invalid unit')
    assert calls == ['invalid unit']


def test_invalid_unit_does_not_touch_installed_services(installer, monkeypatch, tmp_path):
    measuring = tmp_path / 'Measuring'
    python = measuring / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    python.chmod(0o755)
    driver = tmp_path / 'home.py'
    driver.touch()
    monkeypatch.setattr(installer, 'MEASURING', measuring)
    monkeypatch.setattr(installer, 'DRIVER', driver)
    monkeypatch.setattr(installer, 'STATE', tmp_path / 'backup.json')
    monkeypatch.setattr(installer, 'run', lambda *a, **kw: result())
    def invalid(text):
        raise subprocess.CalledProcessError(1, ['systemd-analyze', 'verify'])
    monkeypatch.setattr(installer, 'validate_unit', invalid)
    def forbidden(*a, **kw):
        pytest.fail('No installed service should be changed before validation succeeds')
    monkeypatch.setattr(installer, 'ctl', forbidden)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install()
    assert not installer.STATE.exists()


def test_identify_only_exact_home_driver_services(installer, monkeypatch):
    def ctl(scope, *args, **kwargs):
        if args[0] == 'list-unit-files':
            return result('home.service enabled\nother.service enabled\nmedlock-screen.service enabled\n')
        if args[0] == 'show':
            return result('Id=home.service\nExecStart=/usr/bin/python3 /home/medlock/medlock_home.py\n\n'
                          'Id=other.service\nExecStart=/usr/bin/python3 /home/medlock/medlock_home.py.old\n\n'
                          'Id=medlock-screen.service\nExecStart=/home/medlock/medlock_home.py\n')
        return result('enabled\n')
    monkeypatch.setattr(installer, 'ctl', ctl)
    assert installer.home_services('system') == [
        {'scope': 'system', 'name': 'home.service', 'enabled': True, 'active': True}]


def test_restore_reenables_only_previous_services(installer, monkeypatch):
    calls = []
    monkeypatch.setattr(installer, 'ctl', lambda *a, **kw: calls.append(a) or result())
    monkeypatch.setattr(installer, 'run', lambda *a, **kw: calls.append(a) or result())
    installer.restore({'unit': None, 'services': [
        {'scope': 'system', 'name': 'home.service', 'enabled': True, 'active': True},
        {'scope': 'user', 'name': 'unused.service', 'enabled': False, 'active': False}]})
    assert calls[0] == ('system', 'disable', '--now', installer.UNIT)
    assert ('system', 'enable', 'home.service') in calls
    assert ('system', 'start', 'home.service') in calls
    assert not any('unused.service' in call for call in calls)


def test_failed_start_rolls_back_old_home_screen(installer, monkeypatch, tmp_path):
    measuring = tmp_path / 'Measuring'
    python = measuring / '.venv/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    python.chmod(0o755)
    driver = tmp_path / 'medlock_home.py'
    driver.touch()
    monkeypatch.setattr(installer, 'MEASURING', measuring)
    monkeypatch.setattr(installer, 'DRIVER', driver)
    monkeypatch.setattr(installer, 'UNIT_PATH', tmp_path / 'installed.service')
    monkeypatch.setattr(installer, 'STATE', measuring / 'runtime/backup.json')
    monkeypatch.setattr(installer, 'check_other_launchers', lambda: None)
    service = {'scope': 'system', 'name': 'old-home.service', 'enabled': True, 'active': True}
    monkeypatch.setattr(installer, 'home_services', lambda scope: [service] if scope == 'system' else [])
    monkeypatch.setattr(installer, 'run', lambda *a, **kw: result())
    monkeypatch.setattr(installer, 'write_unit', lambda text: None)
    connection = SimpleNamespace(settimeout=lambda n: None, connect_ex=lambda addr: 1)
    class Socket:
        def __enter__(self): return connection
        def __exit__(self, *args): pass
    monkeypatch.setattr(installer.socket, 'socket', Socket)
    calls = []
    def ctl(scope, *args, **kwargs):
        calls.append((scope, *args))
        if args == ('is-active', installer.UNIT):
            return result(code=3)
        if args == ('start', installer.UNIT):
            raise subprocess.CalledProcessError(1, ['systemctl', 'start'])
        return result()
    monkeypatch.setattr(installer, 'ctl', ctl)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install()
    assert ('system', 'disable', '--now', 'old-home.service') in calls
    assert ('system', 'enable', 'old-home.service') in calls
    assert ('system', 'start', 'old-home.service') in calls
    assert installer.STATE.exists()
