"""Configuration and platform detection for agy-sandbox."""

import os
import platform
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Provider(str, Enum):
    """AI provider type."""
    STUDIO = "studio"
    VERTEX = "vertex"


class Platform(str, Enum):
    """Operating system platform."""
    LINUX = "linux"
    DARWIN = "darwin"
    WINDOWS = "windows"
    OTHER = "other"


def _detect_platform() -> Platform:
    """Detect the current operating system platform."""
    system = platform.system().lower()
    if system == "linux":
        return Platform.LINUX
    elif system == "darwin":
        return Platform.DARWIN
    elif system == "windows":
        return Platform.WINDOWS
    return Platform.OTHER


def _get_username() -> str:
    """Get the current username."""
    return os.environ.get("USER") or os.environ.get("USERNAME") or ""


def _get_uid() -> int:
    """Get the current user's UID."""
    try:
        return os.getuid()
    except (AttributeError, ImportError):
        return 1000


def _get_gid() -> int:
    """Get the current user's GID."""
    try:
        return os.getgid()
    except (AttributeError, ImportError):
        return 1000


def get_docker_socket_path() -> str:
    """Get the Docker socket path for the current platform."""
    return os.environ.get("DOCKER_HOST", "").replace("unix://", "") or "/var/run/docker.sock"


def is_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


@dataclass
class SandboxConfig:
    """Configuration for the sandbox environment."""
    project_dir: Path
    provider: Provider = Provider.STUDIO
    container_name: Optional[str] = None
    image_name: Optional[str] = None
    host_user: str = ""
    host_uid: int = 0
    host_gid: int = 0
    container_home: str = ""
    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "antigravity")
    gemini_config_dir: Path = field(default_factory=lambda: Path.home() / ".gemini")
    platform: Platform = field(default_factory=_detect_platform)

    def __post_init__(self):
        """Set derived fields after initialization."""
        if not self.host_user:
            self.host_user = _get_username()

        if self.host_uid == 0:
            self.host_uid = _get_uid()

        if self.host_gid == 0:
            self.host_gid = _get_gid()

        dir_name = self.project_dir.name
        self.container_name = self.container_name or f"agy-{dir_name}"
        self.image_name = self.image_name or f"antigravity-sandbox-{self.host_uid}"

        # Determine container home directory
        if not self.container_home:
            self.container_home = "/home/ubuntu" if self.host_uid == 1000 else "/home/developer"

        # Platform-specific path adjustments
        if self.platform == Platform.WINDOWS:
            self._adjust_for_windows()

    def _adjust_for_windows(self):
        """Adjust paths for Windows compatibility."""
        # On Windows, Docker typically uses WSL2 or Docker Desktop
        # Home directory paths need to be converted
        pass