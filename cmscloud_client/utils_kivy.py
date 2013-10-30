# -*- coding: utf-8 -*-
import subprocess
import sys

from kivy.logger import Logger
from kivy.properties import ObjectProperty
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from pync import Notifier


class TabTextInput(TextInput):
    next = ObjectProperty(None)

    def _keyboard_on_key_down(self, window, keycode, text, modifiers):
        key, key_str = keycode
        if key in (9, 13) and self.next is not None:
            if isinstance(self.next, TextInput):
                self.next.focus = True
                self.next.select_all()
            if isinstance(self.next, Button):
                self.focus = False
                self.next.dispatch('on_press')
                self.next.dispatch('on_release')
        else:
            super(TabTextInput, self)._keyboard_on_key_down(window, keycode, text, modifiers)


def open_in_file_manager(path):
    platform = sys.platform
    if platform == 'win32':
        subprocess.Popen(['start', path], shell=True)
    elif platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        try:
            subprocess.Popen(['xdg-open', path])
        except OSError:
            Logger.exception('Cannot open external file manager')


def notify(title, message):
    platform = sys.platform
    if platform == 'darwin':
        Notifier.notify(message, title=title)
    else:
        try:
            subprocess.Popen(['notify-send', title, message, '-t', '10000'])
        except OSError:
            Logger.exception('Cannot open external file manager')
