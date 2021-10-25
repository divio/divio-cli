import sys
import traceback

import click
from sentry_sdk import capture_exception
from sentry_sdk.integrations import Integration


def divio_shutdown(pending, timeout):
    pass


def confirmation_excepthook(*exc_info):
    # Print normal stacktrace
    text = "".join(traceback.format_exception(*exc_info))
    click.secho(text)

    click.secho(
        "We would like to gather information about this error via "
        "sentry to improve our product and to resolve this issue "
        "in the future."
    )
    if click.confirm(
        "Do you want to send information about this error to Divio "
        "for debugging purposes and to make the product better?"
    ):
        event_id = capture_exception(exc_info[1])
        click.secho(
            f"Thank you! You can communicate the following ID to support: {event_id}"
        )
    else:
        click.secho("Ok, not sending information :(")


class DivioExcepthookIntegration(Integration):
    identifier = "excepthook"

    @staticmethod
    def setup_once():
        sys.excepthook = confirmation_excepthook
