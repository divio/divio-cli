# -*- coding: utf-8 -*-
from kivy.uix.textinput import TextInput
from kivy.properties import ObjectProperty
from kivy.uix.button import Button


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
