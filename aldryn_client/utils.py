# -*- coding: utf-8 -*-
import click
from tabulate import tabulate


def hr(char='─', width=None, **kwargs):
    if width is None:
        width = click.get_terminal_size()[0]
    click.secho(char * width, **kwargs)


def table(data, headers):
    return tabulate(data, headers)


def indent(text, spaces=4):
    return '\n'.join(' ' * spaces + ln for ln in text.splitlines())
