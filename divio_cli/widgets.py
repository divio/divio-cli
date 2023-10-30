import platform
import readline
from collections.abc import Iterable
from getpass import getpass
from io import StringIO
from textwrap import wrap

import click

from divio_cli.config import WritableNetRC


_config = {
    "interactive": True,
}


def set_non_interactive():
    _config["interactive"] = False


# helper ######################################################################
def get_print_length(string):
    length = 0
    quoted = False

    for character in string:
        if character == "\001":
            quoted = True

        elif character == "\002":
            quoted = False

        elif not quoted:
            length += 1

    return length


def split_choice(user_input):
    return [choice.strip() for choice in user_input.split(",") if choice]


# low-level widgets ###########################################################
def print_info(message):
    if not _config["interactive"]:
        return

    click.echo(message)


def print_warning(message):
    if not _config["interactive"]:
        return

    click.secho(message=message, fg="yellow")


def print_error(message):
    if not _config["interactive"]:
        return

    click.secho(message=message, fg="red")


def print_divio_exception(divio_exception):
    if not _config["interactive"]:
        return

    print_error(str(divio_exception))


class Table:
    def __init__(self):
        self._columns = []
        self._rows = []

    def add_column(self, name, max_width=0, right_aligned=False):
        self._columns.append(
            {
                "name": name,
                "max_width": max_width,
                "right_aligned": right_aligned,
            }
        )

    def add_row(self, row):
        if not isinstance(row, Iterable):
            raise ValueError("rows have to be iterable")

        if len(row) != len(self._columns):
            raise ValueError("invalid row length")

        self._rows.append(row)

    def _write_line(self, buffer, column_widths, character="-", corner="+"):
        for column_width in column_widths:
            buffer.write(corner)
            buffer.write(character * (column_width + 2))

        buffer.write(f"{corner}\n")

    def _write_header(self, buffer, column_widths):
        self._write_line(buffer=buffer, column_widths=column_widths)

        self._write_row(
            buffer=buffer,
            column_widths=column_widths,
            row=[i["name"] for i in self._columns],
        )

        self._write_line(
            buffer=buffer,
            column_widths=column_widths,
            character="=",
        )

    def _write_row(self, buffer, column_widths, row):
        cell_lines = []

        for column_index, cell in enumerate(row):
            cell_lines.append(
                wrap(str(cell).strip(), column_widths[column_index])
            )

        longest_cell_length = max([0] + [len(cell) for cell in cell_lines])

        for line_index in range(longest_cell_length):
            buffer.write("| ")

            for column_index in range(len(cell_lines)):
                if line_index >= len(cell_lines[column_index]):
                    line = ""

                else:
                    line = cell_lines[column_index][line_index]

                if self._columns[column_index]["right_aligned"]:
                    line = line.rjust(column_widths[column_index])

                else:
                    line = line.ljust(column_widths[column_index])

                buffer.write(f"{line} | ")

            buffer.write("\n")

    def _get_column_widths(self):
        column_widths = [0 for _ in range(len(self._columns))]

        for row in self._rows:
            for column_index, cell in enumerate(row):
                cell_lines = str(cell).strip().splitlines()

                longest_cell_line = max(
                    [0]
                    + [
                        get_print_length(cell_line) for cell_line in cell_lines
                    ],
                )

                if longest_cell_line > column_widths[column_index]:
                    column_widths[column_index] = longest_cell_line

        for column_index, column in enumerate(self._columns):
            if (
                column["max_width"] > 0
                and column_widths[column_index] > column["max_width"]
            ):
                column_widths[column_index] = column["max_width"]

        return column_widths

    def render(self, buffer):
        column_widths = self._get_column_widths()
        self._write_header(buffer=buffer, column_widths=column_widths)

        for _row_index, row in enumerate(self._rows):
            self._write_row(
                buffer=buffer,
                column_widths=column_widths,
                row=row,
            )

            self._write_line(buffer=buffer, column_widths=column_widths)

    def __str__(self):
        buffer = StringIO()
        self.render(buffer=buffer)
        buffer.seek(0)

        return buffer.read()

    def __repr__(self):
        return str(self)


def get_user_input(prompt="", default="", password=False, validate=None):
    validators = validate or []

    if not isinstance(validators, (list, tuple)):
        validators = [validators]

    def _pre_input_hook():
        readline.insert_text(default)
        readline.redisplay()

    if default:
        readline.set_pre_input_hook(_pre_input_hook)

    try:
        while True:
            if password:
                user_input = getpass(prompt=prompt)

            else:
                user_input = input(prompt)

            input_has_error = False

            for validator in validators:
                error_message = validator(user_input)

                if isinstance(error_message, str):
                    input_has_error = True
                    print_error(error_message)

            if not input_has_error:
                break

    except (
        KeyboardInterrupt,
        EOFError,
    ):
        print_error("Abort")

        raise SystemExit

    finally:
        if default:
            readline.set_pre_input_hook()

    return user_input


def open_browser(url):

    # this is necessary to work in WSL
    # https://github.com/pallets/click/issues/2154
    wait = False

    if "microsoft-standard" in platform.uname().release:
        wait = True

    click.launch(url, wait)


# high-level widgets ##########################################################
def select_option(
    prompt,
    options,
    multiple=False,
    show_help=True,
    enable_help_option=True,
):

    """
    choice = select_option(
        prompt="Select an option",
        options=[
            ('a', 'Option A', True),  # default
            ('b', 'Option B'),
        ],
    )
    """

    # parse options
    labels = []
    help_texts = []
    default_options = []
    default_options_indexes = []

    for index, option in enumerate(options):
        label, help_text, default = ([*list(option), "", "", False])[0:3]

        if default:
            label = label.upper()
            default_options.append(label)
            default_options_indexes.append(index)

        labels.append(label)
        help_texts.append(help_text)

    if enable_help_option:
        labels.append("?")
        help_texts.append("Show this help text")

    # generate prompt
    if multiple:
        prompt = f"{prompt} [{','.join(labels)}]: "

    else:
        prompt = f"{prompt} [{'/'.join(labels)}]: "

    def print_help():
        longest_label_length = max([len(label) for label in labels])

        for index, label in enumerate(labels):
            line = (
                f" {label.rjust(longest_label_length)} - {help_texts[index]}"
            )

            if label in default_options:
                line = f"{line} (default)"

            print_info(line)

        print_info("")

    # choice helper
    def get_choice_index(choice):
        choice = choice.strip()

        if choice.lower() in labels:
            return labels.index(choice.lower())

        if choice.upper() in labels:
            return labels.index(choice.upper())
        return None

    # main loop
    def validate_user_input(user_input):
        choices = split_choice(user_input)

        if not choices and default_options:
            return None

        if not multiple and len(choices) > 1:
            return f"'{user_input}' is not a valid choice"

        for choice in choices:
            if get_choice_index(choice) is None:
                return f"'{choice}' is not a valid choice"
        return None

    if show_help:
        print_help()

    while True:
        user_input = get_user_input(
            prompt=prompt,
            validate=validate_user_input,
        )

        choices = split_choice(user_input)

        if "?" in choices:
            print_help()

            continue

        break

    # parse result
    if not choices:
        choices_indexes = default_options_indexes

    else:
        choices_indexes = [
            get_choice_index(choice)
            for choice in choices
            if choice is not None
        ]

    if not multiple:
        return choices_indexes[0]

    return choices_indexes


def select_from_range(prompt, choices_range, multiple=False):
    prompt = f"{prompt} [{choices_range.start}..{choices_range.stop}]: "

    def validate_user_input(user_input):
        choices = split_choice(user_input)

        if not multiple and len(choices) > 1:
            return f"'{user_input}' is not a valid choice"

        for choice in choices:
            if not choice.isdigit() or int(choice) not in choices_range:
                return f"'{choice}' is not a valid choice"
        return None

    user_input = get_user_input(
        prompt=prompt,
        validate=validate_user_input,
    )

    if not user_input:
        return None

    choices = [int(choice) for choice in split_choice(user_input)]

    if not multiple:
        return choices[0]

    return choices


def confirm(prompt, default=False):
    if not _config["interactive"]:
        return default

    user_input = select_option(
        prompt=prompt,
        options=[
            ("y", "Yes", default is True),
            ("n", "No", default is False),
        ],
        multiple=False,
        show_help=False,
        enable_help_option=False,
    )

    return user_input == 0


def login(client, token=""):
    netrc = WritableNetRC()

    def validate_token(token):
        distinct_characters = set(token)

        if distinct_characters == {"\x16"}:
            return "The access token provided indicates a copy/paste malfunction.\nRead more here: https://r.divio.com/divio-login-windows-users."

        client.authenticate(token=token)

        if not client.is_authenticated():
            return "Invalid Token"

        return None

    if token:
        error_message = validate_token(token)

        if error_message:
            print_error(error_message)

            return False

    else:
        # get token from control-panel
        open_browser(url=client.get_access_token_url())

        token = get_user_input(
            prompt="Please copy the access token and paste it here. (your input is not displayed)",
            password=True,
            validate=validate_token,
        )

    # add tokens for the control-panel and its API to the netrc
    netrc.add(
        host=client.get_control_panel_host(),
        login=client.get_user_email(),
        account=None,
        password=token,
    )

    netrc.add(
        host=client.get_api_host(),
        login=client.get_user_email(),
        account=None,
        password=token,
    )

    netrc.write()

    # greet user
    print_info(f"Logged in as {client.get_user_name()}")

    return True


def logout(client):
    netrc = WritableNetRC()

    if _config["interactive"]:
        if not confirm(
            prompt=f"Are you sure you want to logout from {client.zone}?",
        ):

            return False

    logged_out = False
    control_panel_host = client.get_control_panel_host()
    api_host = client.get_api_host()

    if control_panel_host in netrc.hosts:
        netrc.remove(control_panel_host)
        logged_out = True

    if api_host in netrc.hosts:
        netrc.remove(api_host)
        logged_out = True

    if logged_out:
        netrc.write()
        print_info(f"Logged out from {client.zone}")

    else:
        print_info(f"You are not logged into {client.zone} at the moment")

    return logged_out
