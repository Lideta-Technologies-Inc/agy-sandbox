import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner
from agy_sandbox.cli import main, AliasedGroup

def test_info_command():
    runner = CliRunner()
    result = runner.invoke(main, ["info"])
    assert result.exit_code == 0
    assert "agy-sandbox information:" in result.output
    assert "Platform:" in result.output
    assert "Username:" in result.output
    assert "UID/GID:" in result.output
    assert "Docker:" in result.output

@patch('agy_sandbox.engine.SandboxEngine.list_containers')
def test_list_command(mock_list):
    runner = CliRunner()
    result = runner.invoke(main, ["list"])
    assert result.exit_code == 0
    mock_list.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.stop')
def test_stop_command(mock_stop):
    runner = CliRunner()
    result = runner.invoke(main, ["stop"])
    assert result.exit_code == 0
    mock_stop.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.stop')
def test_stop_command_with_container_name(mock_stop):
    runner = CliRunner()
    result = runner.invoke(main, ["stop", "agy-some-container"])
    assert result.exit_code == 0
    mock_stop.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.remove')
def test_remove_command(mock_remove):
    runner = CliRunner()
    result = runner.invoke(main, ["remove"])
    assert result.exit_code == 0
    mock_remove.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.remove')
def test_remove_command_with_container_name(mock_remove):
    runner = CliRunner()
    result = runner.invoke(main, ["remove", "agy-some-container"])
    assert result.exit_code == 0
    mock_remove.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.logs')
def test_logs_command(mock_logs, tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["logs", str(tmp_path)])
    assert result.exit_code == 0
    mock_logs.assert_called_once_with(follow=False, tail=100)

@patch('agy_sandbox.engine.SandboxEngine.provision')
def test_provision_command(mock_provision, tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["provision", str(tmp_path), "studio"])
    assert result.exit_code == 0
    mock_provision.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.provision')
def test_aliased_group_routes_path(mock_provision, tmp_path):
    # Testing our AliasedGroup class via CliRunner invoking main with a directory
    runner = CliRunner()
    # Path argument routing
    result = runner.invoke(main, [str(tmp_path)])
    assert result.exit_code == 0
    mock_provision.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.provision')
def test_aliased_group_aliases(mock_provision, tmp_path):
    runner = CliRunner()
    # alias 'up' maps to 'provision'
    result = runner.invoke(main, ["up", str(tmp_path)])
    assert result.exit_code == 0
    mock_provision.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.connect_to_container')
@patch('agy_sandbox.engine.SandboxEngine.check_container_state', return_value='running')
def test_connect_running(mock_state, mock_connect, tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["connect", str(tmp_path)])
    assert result.exit_code == 0
    mock_connect.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.start_container')
@patch('agy_sandbox.engine.SandboxEngine.check_container_state', return_value='stopped')
def test_connect_stopped(mock_state, mock_start, tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["connect", str(tmp_path)])
    assert result.exit_code == 0
    mock_start.assert_called_once()

@patch('agy_sandbox.engine.SandboxEngine.check_container_state', return_value='absent')
def test_connect_absent(mock_state, tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["connect", str(tmp_path)])
    assert result.exit_code == 1
    assert "No container found" in result.output

@patch('agy_sandbox.engine.SandboxEngine.provision', side_effect=ValueError("Test Error"))
def test_provision_docker_error_handling(mock_provision, tmp_path):
    from agy_sandbox.engine import DockerError
    # We must raise a DockerError to check if it exits with 1
    mock_provision.side_effect = DockerError("Specific Docker Failure")
    runner = CliRunner()
    result = runner.invoke(main, ["provision", str(tmp_path)])
    assert result.exit_code == 1
    assert "❌ Error: Specific Docker Failure" in result.output
