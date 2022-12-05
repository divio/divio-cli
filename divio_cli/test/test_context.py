import pytest

from .. import context


def test_context_stack():
    ctx = context.Context()

    with pytest.raises(AttributeError):
        ctx.zone

    ctx.load_global_context()

    assert ctx.zone == "divio.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            app_settings={},
            docker_compose_executor=None,
        )
    ):
        assert ctx.zone == "divio.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            app_settings={},
            docker_compose_executor=None,
            zone="app.com",
        )
    ):
        assert ctx.zone == "app.com"

    assert ctx.zone == "divio.com"


def test_get_git_host():
    ctx = context.Context()
    ctx.load_global_context()

    assert ctx.get_git_host() == "git@git.divio.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            docker_compose_executor=None,
            app_settings={},
        )
    ):
        assert ctx.get_git_host() == "git@git.divio.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            docker_compose_executor=None,
            app_settings={},
            zone="app.com",
        )
    ):
        assert ctx.get_git_host() == "git@git.app.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            docker_compose_executor=None,
            app_settings={"git_host": "user@my.git.host"},
        )
    ):
        assert ctx.get_git_host() == "user@my.git.host"


def test_frame_client():
    ctx = context.Context()
    ctx.load_global_context()

    orig_client = ctx.client
    assert ctx.client.endpoint == "https://control.divio.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            docker_compose_executor=None,
            app_settings={},
        )
    ):
        assert ctx.client is not orig_client
        assert ctx.client.endpoint == "https://control.divio.com"

    with ctx.push(
        context.ApplicationEnvironment(
            app_path="",
            docker_compose_executor=None,
            app_settings={},
            zone="app.com",
        )
    ):
        assert ctx.client is not orig_client
        assert ctx.client.endpoint == "https://control.app.com"

    assert ctx.client is orig_client
    assert ctx.client.endpoint == "https://control.divio.com"
