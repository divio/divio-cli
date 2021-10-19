import sys
import traceback

import click
from sentry_sdk import last_event_id
from sentry_sdk.integrations.excepthook import ExcepthookIntegration


def empty_excepthook(*exc_info):
    pass


def _make_confirmation_excepthook(sentry_excepthook):
    def sentry_confirmation_excepthook(*exc_info):
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
            sentry_excepthook(*exc_info)
            click.secho(
                f"Thank you! The sentry ID for this event is: {last_event_id()}"
            )
        else:
            click.secho("Ok, not sending information :(")

    return sentry_confirmation_excepthook


class DivioExcepthookIntegration(ExcepthookIntegration):
    @staticmethod
    def setup_once():
        # type: () -> None

        # Make an empty except hook because we are introducing our own in
        # combination with sentry later and this one will be called by sentry
        # and we are already handling everything in the other excepthooks.
        sys.excepthook = empty_excepthook

        # Do the default sentry excepthook setup which will overwrite sys.excepthook
        ExcepthookIntegration.setup_once()

        # Wrap the new sentry except hook into our own confirmation check
        sys.excepthook = _make_confirmation_excepthook(sys.excepthook)
