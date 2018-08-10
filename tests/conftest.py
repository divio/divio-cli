
import yaml
import pytest




@pytest.fixture
def docker_compose_yaml():
    return yaml.load("""version: "2"

services:
    web:
        build: "."
        links:
          - "db:postgres"
        ports:
          - "8000:80"
        volumes:
          - ".:/app:rw"
          - "./data:/data:rw"
        command: python manage.py runserver 0.0.0.0:80
        env_file: .env-local

    db:
        image: postgres:9.6-alpine
        environment:
          POSTGRES_DB: "db"
          PGDATA: "/var/lib/postgresql/data/pgdata"
        volumes:
          - "./data/db:/var/lib/postgresql/data:rw"
          - ".:/app:rw"
        """)
