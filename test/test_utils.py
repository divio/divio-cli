import pytest

from divio_cli.utils import normalize_git_url

TESTDATA_GITURL_NORMALIZE = [
    (
        "https://github.com/kinkerl/glowing-octo-succotash.git",
        "https://github.com/kinkerl/glowing-octo-succotash.git",
    ),
    (
        "git://github.com/kinkerl/glowing-octo-succotash.git",
        "git://github.com/kinkerl/glowing-octo-succotash.git",
    ),
    (
        "git@github.com:kinkerl/glowing-octo-succotash.git",
        "ssh://git@github.com/kinkerl/glowing-octo-succotash.git",
    ),
    (
        "git://git.divio.com/ci-test-project-do-not-delete.git",
        "git://git.divio.com/ci-test-project-do-not-delete.git",
    ),
    (
        "ssh://github.com/kinkerl/glowing-octo-succotash.git",
        "ssh://git@github.com/kinkerl/glowing-octo-succotash.git",
    ),
    (
        "ssh://git.divio.com/ci-test-project-do-not-delete.git",
        "ssh://git@git.divio.com/ci-test-project-do-not-delete.git",
    ),
    (
        "ssh://git.DiVIO.com/ci-test-project-do-not-delete.git",
        "ssh://git@git.divio.com/ci-test-project-do-not-delete.git",
    ),
    (
        "SSH://git.DiVIO.com/ci-test-project-do-not-delete.git",
        "ssh://git@git.divio.com/ci-test-project-do-not-delete.git",
    ),
]


@pytest.mark.parametrize("git_url,expected", TESTDATA_GITURL_NORMALIZE)
def test_normalize_git_url(git_url, expected):
    assert normalize_git_url(git_url) == expected
