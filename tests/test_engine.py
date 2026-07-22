import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
from agy_sandbox.config import SandboxConfig, Provider
from agy_sandbox.engine import SandboxEngine, DockerError

def test_find_assets_dir():
    from agy_sandbox.engine import _find_assets_dir
    assets_dir = _find_assets_dir()
    assert assets_dir.exists()
    assert assets_dir.name == "assets"

def test_find_assets_dir_package():
    from agy_sandbox.engine import _find_assets_dir
    # Let's test the importlib files fallback scenario
    with patch('importlib.resources.files') as mock_files:
        mock_traversable = MagicMock()
        mock_traversable.joinpath.return_value = mock_traversable
        mock_traversable.exists.return_value = True
        mock_traversable.as_posix.return_value = "/path/to/assets"
        mock_files.return_value = mock_traversable
        
        with patch('pathlib.Path.exists', return_value=True):
            res = _find_assets_dir()
            # It found something, we are asserting it returns a Path
            assert isinstance(res, Path)

@patch('subprocess.run')
def test_engine_run_success(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.return_value = MagicMock(returncode=0, stdout="test-stdout", stderr="")
    
    result = engine._run(["echo", "hello"])
    assert result.stdout == "test-stdout"
    mock_run.assert_called_once_with(
        ["echo", "hello"],
        check=True,
        capture_output=False,
        text=True,
        timeout=300
    )

@patch('subprocess.run')
def test_engine_run_timeout(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.side_effect = subprocess.TimeoutExpired(["echo", "hello"], timeout=300)
    
    with pytest.raises(DockerError) as excinfo:
        engine._run(["echo", "hello"])
    
    assert "Command timed out: echo hello" in str(excinfo.value)

@patch('subprocess.run')
def test_engine_run_called_process_error(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd=["echo", "hello"],
        stderr="some error message"
    )
    
    with pytest.raises(DockerError) as excinfo:
        engine._run(["echo", "hello"])
    
    assert "Command failed (1): echo hello" in str(excinfo.value)
    assert "some error message" in str(excinfo.value)

@patch('agy_sandbox.engine.is_docker_available')
def test_check_docker(mock_is_docker_available, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_is_docker_available.return_value = True
    assert engine.check_docker() is True
    
    mock_is_docker_available.return_value = False
    assert engine.check_docker() is False

@patch('subprocess.run')
def test_check_container_state_running(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    # We expect ps -q -f name=^agy-tmp_path$ to return something
    mock_run.return_value = MagicMock(returncode=0, stdout="container-id\n", stderr="")
    
    state = engine.check_container_state()
    assert state == "running"

@patch('subprocess.run')
def test_check_container_state_stopped(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    # First ps running check returns empty stdout
    # Second ps -a check returns container-id
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout="container-id\n", stderr="")
    ]
    
    state = engine.check_container_state()
    assert state == "stopped"

@patch('subprocess.run')
def test_check_container_state_absent(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    # Both return empty stdout
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="", stderr=""),
        MagicMock(returncode=0, stdout="", stderr="")
    ]
    
    state = engine.check_container_state()
    assert state == "absent"

@patch('subprocess.run')
def test_check_container_state_error(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.side_effect = subprocess.CalledProcessError(1, ["docker", "ps"])
    assert engine.check_container_state() == "absent"

@patch('subprocess.run')
def test_stop_container(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    # State returns "running" to allow stop command
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="container-id\n", stderr=""), # for check_container_state (is running)
        MagicMock(returncode=0) # for stop command
    ]
    engine.stop()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["docker", "stop", config.container_name],
        check=False,
        capture_output=False,
        text=True,
        timeout=300
    )

@patch('subprocess.run')
def test_remove_container(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    # State returns "running" to allow remove command
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="container-id\n", stderr=""), # for check_container_state (is running)
        MagicMock(returncode=0) # for remove command
    ]
    engine.remove()
    assert mock_run.call_count == 2
    mock_run.assert_any_call(
        ["docker", "rm", "-f", config.container_name],
        check=False,
        capture_output=False,
        text=True,
        timeout=300
    )

@patch('subprocess.run')
def test_build_image_success(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.return_value = MagicMock(returncode=0)
    
    with patch('pathlib.Path.exists', return_value=True):
        engine.build_image()
        
    mock_run.assert_called_once()
    assert "buildx" in mock_run.call_args[0][0]

@patch('pathlib.Path.exists', return_value=False)
def test_build_image_missing_dockerfile(mock_exists, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    with pytest.raises(DockerError) as excinfo:
        engine.build_image()
    assert "Dockerfile not found" in str(excinfo.value)

@patch('pathlib.Path.exists', return_value=True)
@patch('subprocess.run')
def test_run_container(mock_run, mock_exists, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.return_value = MagicMock(returncode=0)
    
    engine.run_container()
    assert mock_run.call_count >= 1

@patch('os.execvp')
def test_exec_interactive(mock_execvp, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    engine._exec_interactive(["exec", "-it", "name"])
    mock_execvp.assert_called_once_with("docker", ["docker", "exec", "-it", "name"])

@patch('agy_sandbox.engine.SandboxEngine._exec_interactive')
def test_connect_to_container(mock_exec, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    engine.connect_to_container()
    mock_exec.assert_called_once_with(["exec", "-it", config.container_name, "agy", "init", "--remote"])

@patch('agy_sandbox.engine.SandboxEngine.connect_to_container')
@patch('subprocess.run')
def test_start_container(mock_run, mock_connect, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.return_value = MagicMock(returncode=0)
    
    engine.start_container()
    mock_run.assert_called_once_with(
        ["docker", "start", config.container_name],
        check=False,
        capture_output=False,
        text=True,
        timeout=300
    )
    mock_connect.assert_called_once()

@patch('subprocess.run')
def test_list_containers(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.return_value = MagicMock(returncode=0, stdout="agy-test running\n")
    engine.list_containers()
    mock_run.assert_called_once()

@patch('subprocess.run')
def test_logs(mock_run, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_run.return_value = MagicMock(returncode=0)
    engine.logs(follow=True, tail=50)
    mock_run.assert_called_once_with(
        ["docker", "logs", "-f", "--tail", "50", config.container_name],
        check=False,
        capture_output=False,
        text=True,
        timeout=300
    )

@patch('agy_sandbox.engine.SandboxEngine.check_docker')
@patch('agy_sandbox.engine.SandboxEngine.check_container_state')
@patch('agy_sandbox.engine.SandboxEngine.connect_to_container')
def test_provision_running(mock_connect, mock_state, mock_check_docker, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_check_docker.return_value = True
    mock_state.return_value = "running"
    
    engine.provision()
    mock_connect.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.check_docker')
@patch('agy_sandbox.engine.SandboxEngine.check_container_state')
@patch('agy_sandbox.engine.SandboxEngine.start_container')
def test_provision_stopped(mock_start, mock_state, mock_check_docker, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_check_docker.return_value = True
    mock_state.return_value = "stopped"
    
    engine.provision()
    mock_start.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.check_docker')
@patch('agy_sandbox.engine.SandboxEngine.check_container_state')
@patch('agy_sandbox.engine.SandboxEngine.build_image')
@patch('agy_sandbox.engine.SandboxEngine.run_container')
@patch('agy_sandbox.engine.SandboxEngine.connect_to_container')
def test_provision_absent(mock_connect, mock_run, mock_build, mock_state, mock_check_docker, tmp_path):
    config = SandboxConfig(project_dir=tmp_path)
    engine = SandboxEngine(config)
    
    mock_check_docker.return_value = True
    mock_state.return_value = "absent"
    
    engine.provision()
    mock_build.assert_called_once()
    mock_run.assert_called_once()
    mock_connect.assert_called_once()

def test_get_provider_args_vertex(tmp_path):
    config = SandboxConfig(project_dir=tmp_path, provider=Provider.VERTEX)
    engine = SandboxEngine(config)
    
    # Should fail with custom sys.exit if ADC doesn't exist
    with patch('pathlib.Path.exists', return_value=False):
        with pytest.raises(SystemExit) as excinfo:
            engine.get_provider_args()
        assert excinfo.value.code == 1
        
    with patch('pathlib.Path.exists', return_value=True):
        args = engine.get_provider_args()
        assert "GOOGLE_APPLICATION_CREDENTIALS" in "".join(args)
