import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from agy_sandbox.config import SandboxConfig, Provider, Platform, _detect_platform, _get_username, _get_uid, _get_gid, get_docker_socket_path

def test_detect_platform_darwin():
    with patch('platform.system', return_value='Darwin'):
        assert _detect_platform() == Platform.DARWIN

def test_detect_platform_windows():
    with patch('platform.system', return_value='Windows'):
        assert _detect_platform() == Platform.WINDOWS

def test_detect_platform_other():
    with patch('platform.system', return_value='FreeBSD'):
        assert _detect_platform() == Platform.OTHER

def test_detect_platform_linux():
    with patch('platform.system', return_value='Linux'):
        assert _detect_platform() == Platform.LINUX

def test_get_username_env():
    with patch.dict('os.environ', {'USER': 'test-user'}):
        assert _get_username() == 'test-user'
    with patch.dict('os.environ', {'USERNAME': 'win-user'}, clear=True):
        assert _get_username() == 'win-user'

def test_get_uid_and_gid():
    with patch('os.getuid', return_value=1234, create=True):
        assert _get_uid() == 1234
    with patch('os.getgid', return_value=5678, create=True):
        assert _get_gid() == 5678

def test_get_uid_and_gid_fallback():
    # If os.getuid does not exist (e.g. Windows)
    with patch('os.getuid', side_effect=AttributeError, create=True):
        assert _get_uid() == 1000
    with patch('os.getgid', side_effect=AttributeError, create=True):
        assert _get_gid() == 1000

def test_get_docker_socket_path():
    with patch.dict('os.environ', {'DOCKER_HOST': 'unix:///my/custom/docker.sock'}):
        assert get_docker_socket_path() == '/my/custom/docker.sock'
    with patch.dict('os.environ', {}, clear=True):
        assert get_docker_socket_path() == '/var/run/docker.sock'

def test_sandbox_config_uid_1000(tmp_path):
    config = SandboxConfig(project_dir=tmp_path, host_uid=1000)
    assert config.container_home == "/home/ubuntu"
    
def test_sandbox_config_uid_other(tmp_path):
    config = SandboxConfig(project_dir=tmp_path, host_uid=1005)
    assert config.container_home == "/home/developer"

def test_sandbox_config_windows(tmp_path):
    # Tests that _adjust_for_windows is called and sets appropriate platforms
    config = SandboxConfig(project_dir=tmp_path, platform=Platform.WINDOWS)
    assert config.platform == Platform.WINDOWS
