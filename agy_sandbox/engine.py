"""Core engine for managing Docker-based sandbox environments."""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from .config import SandboxConfig, Provider, is_docker_available


class DockerError(Exception):
    """Raised when Docker operations fail."""
    pass


def _find_assets_dir() -> Path:
    """Find the assets directory containing Dockerfiles.

    Works both when installed as a package and when running from source.
    """
    # Try package resources first (installed package)
    try:
        import importlib.resources
        assets = importlib.resources.files("agy_sandbox").joinpath("assets")
        # In Python 3.11+, files() returns a Traversable that may be a Path
        if hasattr(assets, 'as_posix'):
            assets_path = Path(assets) if not isinstance(assets, Path) else assets
            if assets_path.exists():
                return assets_path
    except (ImportError, OSError):
        pass

    # Fall back to source directory structure
    current = Path(__file__).resolve().parent
    assets = current / "assets"
    if assets.exists():
        return assets

    # Last resort: look in parent directories (development)
    for parent in current.parents:
        candidate = parent / "assets"
        if candidate.exists():
            return candidate

    return current / "assets"  # fallback to same directory


class SandboxEngine:
    """Manages the lifecycle of Docker-based sandbox environments."""

    def __init__(self, config: SandboxConfig):
        """Initialize the sandbox engine.

        Args:
            config: The sandbox configuration.
        """
        self.config = config
        self.script_dir = _find_assets_dir()

    def _run(self, args: List[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
        """Run a subprocess command.

        Args:
            args: Command arguments.
            check: Whether to raise on non-zero exit.
            capture: Whether to capture output.

        Returns:
            CompletedProcess instance.
        """
        try:
            return subprocess.run(
                args,
                check=check,
                capture_output=capture,
                text=True,
                timeout=300
            )
        except subprocess.TimeoutExpired as e:
            raise DockerError(f"Command timed out: {' '.join(args)}") from e
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else "No error output"
            raise DockerError(f"Command failed ({e.returncode}): {' '.join(args)}\n{stderr}") from e

    def _docker(self, args: List[str], check: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
        """Run a docker command.

        Args:
            args: Docker subcommand and arguments.
            check: Whether to raise on non-zero exit.
            capture: Whether to capture output.

        Returns:
            CompletedProcess instance.
        """
        cmd = ["docker"] + args
        return self._run(cmd, check=check, capture=capture)

    def check_docker(self) -> bool:
        """Check if Docker is available and running."""
        if not is_docker_available():
            print("❌ Docker is not available or not running. Please install/start Docker first.")
            return False
        return True

    def check_container_state(self) -> str:
        """Check the state of the container.

        Returns:
            'running', 'stopped', or 'absent'
        """
        try:
            # Check if running
            result = self._docker(
                ["ps", "-q", "-f", f"name=^{self.config.container_name}$"],
                capture=True
            )
            if result.stdout.strip():
                return "running"

            # Check if exists but stopped
            result = self._docker(
                ["ps", "-a", "-q", "-f", f"name=^{self.config.container_name}$"],
                capture=True
            )
            if result.stdout.strip():
                return "stopped"

            return "absent"
        except DockerError:
            return "absent"

    def build_image(self) -> None:
        """Build the Docker image for the sandbox."""
        dockerfile = self.script_dir / "Dockerfile_permissive"
        if not dockerfile.exists():
            raise DockerError(f"Dockerfile not found at {dockerfile}")

        print(f"Building base Docker image '{self.config.image_name}'...")

        # Use buildx directly — buildx requires --build-arg AFTER the 'build' subcommand
        build_args = [
            "buildx", "build",
            f"--build-arg=USER_UID={self.config.host_uid}",
            f"--build-arg=USER_GID={self.config.host_gid}",
            "-f", str(dockerfile),
            "-t", self.config.image_name,
            "--load",
            str(self.script_dir)
        ]

        self._docker(build_args)
        print(f"✔ Image '{self.config.image_name}' built successfully.")

    def get_provider_args(self) -> List[str]:
        """Get Docker arguments based on the selected provider.

        Returns:
            List of docker run arguments.
        """
        args = []

        if self.config.provider == Provider.VERTEX:
            adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
            if not adc_path.exists():
                print(f"❌ Error: ADC credentials file not found at '{adc_path}'.")
                print("Please run this command on your host first to log in:")
                print("  gcloud auth application-default login")
                sys.exit(1)

            home = Path.home()
            gcloud_path = home / ".config" / "gcloud"
            args.extend([
                "-v", f"{gcloud_path}:{self.config.container_home}/.config/gcloud:ro",
                "-e", f"GOOGLE_APPLICATION_CREDENTIALS={self.config.container_home}/.config/gcloud/application_default_credentials.json",
                "-e", "CLOUD_SDK_PROJECT=lideta-products",
                "-e", "GOOGLE_CLOUD_PROJECT=lideta-products",
            ])
            print("✦ Configured container to use Vertex AI with host credentials.")

        else:  # studio
            gemini_key = os.environ.get("GEMINI_API_KEY")
            if gemini_key:
                args.extend(["-e", f"GEMINI_API_KEY={gemini_key}"])
            print("✦ Configured container to use Google AI Studio.")

        return args

    def _get_volume_mounts(self) -> List[str]:
        """Get volume mount arguments for the container."""
        home = Path.home()
        mounts = [
            f"{self.config.project_dir}:/workspace",
            f"{self.config.config_dir}:{self.config.container_home}/.config/antigravity",
            f"{self.config.gemini_config_dir}:{self.config.container_home}/.gemini_host:ro",
        ]

        # Platform-specific cache paths
        if self.config.platform.value == "windows":
            # On Windows, paths are already compatible with Docker Desktop/WSL2
            pass
        mounts.extend([
            f"{home / '.cache' / 'uv'}:{self.config.container_home}/.cache/uv",
            f"{home / '.local' / 'share' / 'uv'}:{self.config.container_home}/.local/share/uv",
        ])

        return mounts

    def run_container(self) -> None:
        """Run the sandbox container."""
        print("Spawning background sandbox daemon...")

        cmd = [
            "run", "-d",
            "--name", self.config.container_name,
            "--restart", "unless-stopped",
        ]

        # Add volume mounts
        for mount in self._get_volume_mounts():
            cmd.extend(["-v", mount])

        # Add provider args
        cmd.extend(self.get_provider_args())

        # Add image and command
        cmd.extend([self.config.image_name, "tail", "-f", "/dev/null"])

        self._docker(cmd)

        # Wait for container to fully start
        time.sleep(1.5)

        print(f"✔ Sandbox '{self.config.container_name}' successfully initialized!")

    def _exec_interactive(self, args: List[str]) -> None:
        """Execute a docker command interactively, replacing the current process.

        This avoids subprocess timeouts and passes the terminal directly to docker.
        """
        cmd = ["docker"] + args
        os.execvp("docker", cmd)

    def connect_to_container(self) -> None:
        """Connect to an existing container and start the antigravity session.

        Runs 'agy init --remote' which provides the interactive antigravity session.
        This matches the behavior of the reference manage-agy.sh script.
        """
        # Always run agy init --remote — it provides the interactive session directly
        self._exec_interactive(["exec", "-it", self.config.container_name, "agy", "init", "--remote"])

    def start_container(self) -> None:
        """Start a stopped container."""
        print(f"⚠ Container '{self.config.container_name}' exists but is stopped. Waking it up...")
        self._docker(["start", self.config.container_name])
        self.connect_to_container()

    def provision(self) -> None:
        """Provision and start the sandbox.

        This is the main entry point that orchestrates the full provisioning process.
        """
        if not self.check_docker():
            sys.exit(1)

        state = self.check_container_state()

        if state == "running":
            print(f"✔ Container '{self.config.container_name}' is already running.")
            print("Connecting to your active remote agent workspace...")
            self.connect_to_container()

        elif state == "stopped":
            self.start_container()

        else:
            print("➜ Project sandbox not found. Provisioning clean infrastructure...")
            self.build_image()
            self.run_container()
            # Initialize the agent
            time.sleep(1.5)
            self.connect_to_container()

    def stop(self) -> None:
        """Stop the sandbox container."""
        state = self.check_container_state()
        if state == "absent":
            print(f"✔ Sandbox '{self.config.container_name}' is not running or does not exist.")
            return
        elif state == "stopped":
            print(f"✔ Sandbox '{self.config.container_name}' is already stopped.")
            return

        print(f"Stopping sandbox '{self.config.container_name}'...")
        self._docker(["stop", self.config.container_name])
        print(f"✔ Sandbox '{self.config.container_name}' stopped.")

    def remove(self) -> None:
        """Remove the sandbox container."""
        state = self.check_container_state()
        if state == "absent":
            print(f"✔ Sandbox '{self.config.container_name}' does not exist.")
            return

        print(f"Removing sandbox '{self.config.container_name}'...")
        self._docker(["rm", "-f", self.config.container_name])
        print(f"✔ Sandbox '{self.config.container_name}' removed.")

    def list_containers(self) -> None:
        """List all agy-sandbox containers."""
        result = self._docker(["ps", "-a", "-f", "name=^agy-", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"], capture=True)
        if result.stdout.strip():
            print(result.stdout)
        else:
            print("No agy-sandbox containers found.")

    def logs(self, follow: bool = False, tail: int = 100) -> None:
        """Show container logs.

        Args:
            follow: Follow log output.
            tail: Number of lines to show from the end.
        """
        args = ["logs"]
        if follow:
            args.append("-f")
        if tail:
            args.extend(["--tail", str(tail)])
        args.append(self.config.container_name)
        self._docker(args)