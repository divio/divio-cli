#!/usr/bin/env python
import os

from kivy.app import App
from kivy.config import Config
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.popup import Popup
from kivy.uix.tabbedpanel import TabbedPanelHeader
from pygments.lexers import PythonLexer, YamlLexer

from cmscloud_client.client import Client


DEFAULT_DIR = os.path.expanduser('~')
DEFAULT_HEIGHT = 600
DEFAULT_WIDTH = 960
KNOWN_CONFIG_FILES_FILTERS = ['*.yaml', '*.py']
LAST_DIR = 'last_dir'
USER_SETTINGS_SECTION = 'user_settings'


class DialogField(BoxLayout):
    pass


class LoginDialog(BoxLayout):
    login = ObjectProperty(None)
    cancel = ObjectProperty(None)
    email = ObjectProperty(None)
    password = ObjectProperty(None)


class InfoDialog(BoxLayout):
    close = ObjectProperty(None)
    message_label = ObjectProperty(None)


class Preview(BoxLayout):
    panel = ObjectProperty(None)


class PreviewPanelHeader(TabbedPanelHeader):
    pass


class NoAppDetected(FloatLayout):
    message_label = ObjectProperty(None)


class CodePreview(BoxLayout):
    code_input = ObjectProperty(None)


class Root(FloatLayout):
    file_chooser = ObjectProperty(None)
    content = ObjectProperty(None)
    preview = ObjectProperty(None)
    no_app_view = ObjectProperty(None)
    logged_as = ObjectProperty(None)
    login_button = ObjectProperty(None)


class CMSCloudGUIApp(App):

    def __init__(self, *args, **kwargs):
        # setting app's window size
        Config.set('graphics', 'width', DEFAULT_WIDTH)
        Config.set('graphics', 'height', DEFAULT_HEIGHT)
        Config.write()

        super(CMSCloudGUIApp, self).__init__(*args, **kwargs)
        self.client = Client(os.environ.get(Client.CMSCLOUD_HOST_KEY, Client.CMSCLOUD_HOST_DEFAULT))

    def build_config(self, config):
        config.setdefaults(USER_SETTINGS_SECTION, {
            LAST_DIR: DEFAULT_DIR
        })

    def build(self):
        return Root()

    def on_start(self):
        self._setup_properties()
        if self.client.is_logged_in():
            self._set_logout_button()
        else:
            self._set_login_button()
            self.show_login()
        super(CMSCloudGUIApp, self).on_start()

    def on_stop(self):
        self.config.write()
        super(CMSCloudGUIApp, self).on_stop()

    def dismiss_login_popup(self):
        if self._login_popup:
            self._login_popup.dismiss()

    def dismiss_info_popup(self):
        if self._error_popup:
            self._error_popup.dismiss()

    def show_login(self):
        content = LoginDialog(login=self.login, cancel=self.dismiss_login_popup)
        self._login_popup = Popup(title='Login', content=content, size_hint=(None, None),
                                  size=(300, 200))
        self._login_popup.open()

    def show_dialog(self, title, msg):
        content = InfoDialog(close=self.dismiss_info_popup)
        content.message_label.text = msg
        self._error_popup = Popup(title=title, content=content, size_hint=(None, None),
                                  size=(500, 200))
        self._error_popup.open()

    def _set_login_button(self):
        self.root.logged_as.text = ''
        self.root.login_button.text = 'Login'
        self.root.login_button.on_press = self.show_login

    def _set_logout_button(self):
        self.root.logged_as.text = self.client.get_login()
        self.root.login_button.text = 'Logout'
        self.root.login_button.on_press = self.logout

    def login(self, email, password):
        status, msg = self.client.login(email=email, password=password)
        if status:
            self._set_logout_button()
            self.dismiss_login_popup()
        else:
            self.show_dialog('Error', msg)

    def logout(self):
        self.client.logout(interactive=False)
        self._set_login_button()

    def validate_app(self):
        status, msg = self.client.validate_app(path=self.get_current_dir())
        if status:
            self.show_dialog('Result', msg)
        else:
            self.show_dialog('Error', msg)

    def upload_app(self):
        status, msg = self.client.upload_app(path=self.get_current_dir())
        if status:
            self.show_dialog('Result', msg)
        else:
            self.show_dialog('Error', msg)

    def validate_boilerplate(self):
        status, msg = self.client.validate_boilerplate(path=self.get_current_dir())
        if status:
            self.show_dialog('Result', msg)
        else:
            self.show_dialog('Error', msg)

    def upload_boilerplate(self):
        status, msg = self.client.upload_boilerplate(path=self.get_current_dir())
        if status:
            self.show_dialog('Result', msg)
        else:
            self.show_dialog('Error', msg)

    def sync(self):
        print 'syncing'
        status, msg = self.client.sync(path=self.get_current_dir(), interactive=False)
        if status:
            self.show_dialog('Result', msg)
        else:
            self.show_dialog('Error', msg)

    def get_current_dir(self):
        return self.root.file_chooser.path

    def _show_current_dir_content(self, path):
        self._set_last_dir(path)

        panel = self.root.preview.panel
        panel.clear_widgets()
        panel.clear_tabs()

        tab_selected = False
        for filename in Client.ALL_CONFIG_FILES:
            fullpath = os.path.join(path, filename)
            if os.path.exists(fullpath):
                code_preview = CodePreview()
                if filename.endswith('.yaml'):
                    code_preview.lexer = YamlLexer()
                elif filename.endswith('.py'):
                    code_preview.lexer = PythonLexer()
                with open(fullpath, 'r') as f:
                    source = f.read()
                    try:
                        code_preview.code_input.text = source
                    except UnicodeDecodeError:
                        code_preview.code_input.text = source.decode('utf-8')
                tab = PreviewPanelHeader(text=filename)
                tab.content = code_preview
                panel.add_widget(tab)
                if not tab_selected:
                    panel.default_tab = tab
                    tab_selected = True

        self.root.content.clear_widgets()
        if tab_selected:
            self.root.content.add_widget(self.root.preview)
        else:
            self.root.content.add_widget(self.root.no_app_view)

    def _set_last_dir(self, path):
        self.config.set(USER_SETTINGS_SECTION, LAST_DIR, path)

    def _get_last_dir(self):
        return self.config.getdefault(USER_SETTINGS_SECTION, LAST_DIR, DEFAULT_DIR)

    def _setup_properties(self):
        last_dir = self._get_last_dir()
        file_chooser = self.root.file_chooser
        file_chooser.path = last_dir
        file_chooser.bind(path=lambda instance, path: self._show_current_dir_content(path))
        self._show_current_dir_content(last_dir)
        file_chooser.dirselect = False
        file_chooser.filter_dirs = False
        file_chooser.filters = KNOWN_CONFIG_FILES_FILTERS


if __name__ == '__main__':
    CMSCloudGUIApp().run()
