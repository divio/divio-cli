

from divio_cli.localdev.utils import prepare_yaml_for_windows

def test_prepare_yaml_for_windows(docker_compose_yaml):
    win_conf =  prepare_yaml_for_windows(docker_compose_yaml)
    assert "./data/db:/var/lib/postgresql/data:rw" not in win_conf["services"]["db"]["volumes"]
    assert "/var/lib/postgresql/data" in win_conf["services"]["db"]["volumes"]
    assert ".:/app:rw" in win_conf["services"]["db"]["volumes"]

    assert "PGDATA" not in win_conf["services"]["db"]["environment"]
    assert "POSTGRES_DB" in win_conf["services"]["db"]["environment"]
