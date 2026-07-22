"""Command-line interface for agy-sandbox."""

import sys
from pathlib import Path

import click

from .config import SandboxConfig, Provider
from .engine import SandboxEngine, DockerError


class AliasedGroup(click.Group):
    """Click group that supports command aliases and auto-routes path arguments to 'provision'."""

    ALIASES = {
        "up": "provision",
        "start": "provision",
        "run": "provision",
        "stop": "stop",
        "rm": "remove",
        "remove": "remove",
        "ls": "list",
        "list-containers": "list",
        "logs": "logs",
    }

    def get_command(self, ctx, cmd_name):
        """Resolve aliases to real commands, or auto-route path arguments to 'provision'."""
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            return cmd
        # Check if it's an alias
        resolved = self.ALIASES.get(cmd_name.lower())
        if resolved:
            return self.get_command(ctx, resolved)
        # If cmd_name looks like a directory path, auto-route to 'provision'
        try:
            p = Path(cmd_name)
            if p.is_dir():
                return self.get_command(ctx, "provision")
        except (OSError, ValueError):
            pass
        return None

    def resolve_command(self, ctx, args):
        """Resolve the first argument: alias, path->provision, or real command name."""
        if args and args[0] in self.ALIASES:
            cmd_name = self.ALIASES[args[0]]
            args = [cmd_name] + args[1:]
            return super().resolve_command(ctx, args)
        # Check if first arg is a directory path -> route to provision
        if args:
            try:
                p = Path(args[0])
                if p.is_dir():
                    args = ["provision"] + args
                    return super().resolve_command(ctx, args)
            except (OSError, ValueError):
                pass
        return super().resolve_command(ctx, args)


@click.group(cls=AliasedGroup)
@click.version_option(version="0.1.0", prog_name="agy-sandbox")
@click.pass_context
def main(ctx):
    """agy-sandbox: Secure, isolated development environments with Antigravity AI.

    Spin up containerized sandbox environments for AI-assisted development.
    Each project gets its own isolated container with persistent configuration.

    QUICK START:

    \b
        agy-sandbox /path/to/project          # Start sandbox (default: AI Studio)
        agy-sandbox /path/to/project vertex   # Start with Vertex AI
        agy-sandbox list                      # List all containers
        agy-sandbox stop                      # Stop a container
    """
    ctx.ensure_object(dict)
    ctx.obj["engine"] = None


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument(
    "provider",
    type=click.Choice(["studio", "vertex"], case_sensitive=False),
    required=False,
    default="studio",
)
@click.option(
    "--container-name", "-n",
    help="Custom container name (default: agy-<project-name>)"
)
@click.option(
    "--image-name", "-i",
    help="Custom image name (default: antigravity-sandbox-<uid>)"
)
@click.pass_context
def provision(ctx, project_path, provider, container_name, image_name):
    """Provision and start a sandbox for the given project directory."""
    provider_enum = Provider(provider)

    config = SandboxConfig(
        project_dir=project_path.resolve(),
        provider=provider_enum,
        container_name=container_name,
        image_name=image_name,
    )

    engine = SandboxEngine(config)
    ctx.obj["engine"] = engine

    print("=" * 56)
    click.echo(f"Target Project:   {config.project_dir}")
    click.echo(f"Container Name:   {config.container_name}")
    click.echo(f"Mapping Host ID:  {config.host_uid}:{config.host_gid}")
    click.echo(f"Selected Provider: {provider}")
    click.echo("=" * 56)

    try:
        engine.provision()
    except DockerError as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--provider", "-p",
    type=click.Choice(["studio", "vertex"], case_sensitive=False),
    default="studio",
    help="AI provider to use (default: studio)"
)
@click.pass_context
def connect(ctx, project_path, provider):
    """Connect to an existing sandbox container."""
    config = SandboxConfig(
        project_dir=project_path.resolve(),
        provider=Provider(provider),
    )

    engine = SandboxEngine(config)
    ctx.obj["engine"] = engine

    state = engine.check_container_state()

    if state == "running":
        click.echo(f"Connecting to active sandbox '{config.container_name}'...")
        engine.connect_to_container()
    elif state == "stopped":
        click.echo(f"Starting stopped sandbox '{config.container_name}'...")
        engine.start_container()
    else:
        click.echo(f"No container found for '{config.container_name}'. Use 'provision' first.")
        sys.exit(1)


@main.command()
@click.pass_context
def list(ctx):
    """List all agy-sandbox containers."""
    config = SandboxConfig(project_dir=Path.cwd())
    engine = SandboxEngine(config)
    engine.list_containers()


@main.command()
@click.argument("project_path_or_container", required=False, default=".")
@click.pass_context
def stop(ctx, project_path_or_container):
    """Stop the sandbox container. Accepts an optional project path or container name."""
    # Check if the argument is a container name (starts with agy- or is an active container)
    p = Path(project_path_or_container)
    if project_path_or_container.startswith("agy-") or not p.exists():
        # Treat as direct container name
        config = SandboxConfig(project_dir=Path.cwd(), container_name=project_path_or_container)
    else:
        config = SandboxConfig(project_dir=p.resolve())

    engine = SandboxEngine(config)
    engine.stop()


@main.command()
@click.argument("project_path_or_container", required=False, default=".")
@click.pass_context
def remove(ctx, project_path_or_container):
    """Remove the sandbox container. Accepts an optional project path or container name."""
    p = Path(project_path_or_container)
    if project_path_or_container.startswith("agy-") or not p.exists():
        # Treat as direct container name
        config = SandboxConfig(project_dir=Path.cwd(), container_name=project_path_or_container)
    else:
        config = SandboxConfig(project_dir=p.resolve())

    engine = SandboxEngine(config)
    engine.remove()


@main.command()
@click.argument("project_path", type=click.Path(exists=True, file_okay=False, path_type=Path), default=".")
@click.option("--follow", "-f", is_flag=True, help="Follow log output.")
@click.option("--tail", "-t", type=int, default=100, help="Number of lines from the end.")
@click.pass_context
def logs(ctx, project_path, follow, tail):
    """Show logs from the sandbox container."""
    config = SandboxConfig(project_dir=project_path.resolve())
    engine = SandboxEngine(config)
    engine.logs(follow=follow, tail=tail)


@main.command()
def info():
    """Show system information and Docker status."""
    from .config import _detect_platform, _get_username, _get_uid, _get_gid, is_docker_available

    platform = _detect_platform()
    username = _get_username()
    uid = _get_uid()
    gid = _get_gid()
    docker_ok = is_docker_available()

    click.echo("agy-sandbox information:")
    click.echo(f"  Platform:     {platform.value}")
    click.echo(f"  Username:     {username}")
    click.echo(f"  UID/GID:      {uid}/{gid}")
    click.echo(f"  Docker:       {'Available' if docker_ok else 'Not available'}")
    click.echo(f"  Python:       {sys.version.split()[0]}")


if __name__ == "__main__":
    main()