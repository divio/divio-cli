import os
import subprocess
from pathlib import Path
from functools import update_wrapper

from attr import define, field, frozen, evolve
import click
from click.globals import get_current_context

from . import utils
from .config import Config
from .cloud import CloudClient
from .localdev import utils as localdev_utils


NOT_PROVIDED = object()
DEFAULT_ZONE = "divio.com"
CONTROL_PANEL_ENDPOINT = "https://control.{zone}"
GIT_CLONE_URL = "{git_host}:{project_slug}.git"
DEFAULT_GIT_HOST = "git@git.{divio_zone}"


@frozen
class StackedContext:
    _stack: list = field(factory=lambda: [(None, {})])

    def __getattr__(self, name):
        if name.startswith("_"):
            return super().__getattr__(name)

        for frame, cache in reversed(self._stack[1:]):
            if (
                value := getattr(frame, name, NOT_PROVIDED)
            ) is not NOT_PROVIDED:
                return value

        raise AttributeError(name)

    def push(self, data):
        self._stack.append((data, {}))
        return self

    def pop(self):
        assert len(self._stack) > 1
        self._stack.pop()
        return self

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.pop()


@frozen
class FrameProperty:
    name = field()
    func = field()

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        cache = obj._stack[-1][1]
        try:
            value = cache[self.name]
        except KeyError:
            value = self.func(obj)
            cache[self.name] = value
        return value


def frame_property(func):
    return FrameProperty(func.__name__, func)


@frozen
class Context(StackedContext):
    @frame_property
    def client(self):
        return CloudClient(
            self.get_control_panel_endpoint(),
            debug=self.debug,
            sudo=self.sudo,
            config=self.config,
        )

    @frame_property
    def has_docker_compose(self):
        return self.docker_compose_executor is not None

    @frame_property
    def docker_compose_config(self):
        return localdev_utils.DockerComposeConfig.load_from_yaml(
            self.docker_compose("config", capture=True)
        )

    def docker_compose(
        self,
        *args,
        check=True,
        capture=False,
        capture_err=False,
        catch=True,
        silent=False,
        **kwargs,
    ):
        if check and not capture:
            wrapper = utils.check_call
        elif check and capture:
            wrapper = utils.check_output

        if capture_err:
            assert capture
            stderr = subprocess.STDOUT
        else:
            stderr = kwargs.pop("stderr", None)

        return wrapper(
            self.docker_compose_executor(*args),
            catch=catch,
            silent=silent,
            stderr=stderr,
            **kwargs,
        )

    def get_control_panel_endpoint(self):
        if self.zone != DEFAULT_ZONE:
            click.secho("Using zone: {}\n".format(self.zone), fg="green")
        endpoint = CONTROL_PANEL_ENDPOINT.format(zone=self.zone)
        return endpoint

    def get_git_host(self):
        if self.git_host_override:
            # TODO: Warning
            click.secho(
                "Using custom git host {}\n".format(self.git_host_override),
                fg="yellow",
            )
            return self.git_host_override

        return DEFAULT_GIT_HOST.format(divio_zone=self.zone)

    def get_git_clone_url(self, slug, website_id):
        remote_dsn = self.client.get_repository_dsn(website_id)

        if remote_dsn:
            # If we could get a remote dsn, use it. Otherwise, it's probably a
            # default git setup.
            return remote_dsn

        # TODO: mirrors should fail here

        return GIT_CLONE_URL.format(
            git_host=self.get_git_host(),
            project_slug=slug,
        )

    def load_global_context(self, **kwargs):
        return self.push(GlobalEnvironment(**kwargs))

    def load_application_context(self, path=None):
        application_home = (
            Path(path)
            if path is not None
            else localdev_utils.get_application_home(self.execution_path)
        )
        return self.push(
            ApplicationEnvironment.load_from_path(
                path=application_home,
            )
        )


class ContextPasser:
    def __init__(self, require_app=False, allow_remote_id_override=False):
        self.require_app = require_app
        self.allow_remote_id_override = allow_remote_id_override

    def __call__(self, f):
        def new_func(*args, remote_id=None, **kwargs):
            ctx = get_current_context().obj
            if (
                self.require_app
                or self.allow_remote_id_override
                and not remote_id
            ):
                ctx.load_application_context()
            if self.allow_remote_id_override and remote_id:
                # TODO: Overridden environment
                pass
            if self.allow_remote_id_override:
                kwargs["remote_id"] = remote_id or ctx.app_id
            return f(ctx, *args, **kwargs)

        if self.allow_remote_id_override:
            new_func = click.option(
                "--remote-id",
                "remote_id",
                default=None,
                type=int,
                help=(
                    "Remote Project ID to use for project commands. "
                    "Defaults to the project in the current directory using "
                    "the configuration file."
                ),
            )(new_func)

        return update_wrapper(new_func, f)


pass_cli_context = ContextPasser


@frozen(kw_only=True)
class GlobalEnvironment:
    config: Config = field(factory=Config)
    zone: str = field(default=DEFAULT_ZONE)
    sudo: bool = field(default=False)
    debug: bool = field(default=False)
    execution_path: Path = field(factory=lambda: Path(os.getcwd()))
    git_host_override: str = field(default=None)


@frozen(kw_only=True)
class ApplicationEnvironment:
    app_path: Path = field()
    app_settings = field()
    docker_compose_executor = field(default=NOT_PROVIDED)
    zone = field(default=NOT_PROVIDED)

    @classmethod
    def load_from_path(cls, path):
        settings = localdev_utils.get_project_settings(path)
        try:
            docker_compose_executor = localdev_utils.get_docker_compose_cmd(
                path
            )
        except RuntimeError:
            docker_compose_executor = None

        return cls(
            app_path=path,
            app_settings=settings,
            docker_compose_executor=docker_compose_executor,
        )

    @property
    def git_host_override(self):
        return self.app_settings.get("git_host", None) or NOT_PROVIDED

    @property
    def app_id(self):
        return self.app_settings["id"]

    @property
    def app_slug(self):
        return self.app_settings["slug"]
