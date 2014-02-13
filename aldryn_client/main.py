# -*- coding: utf-8 -*-
# Configuring kivy
# window's sizes and position
WIDTH_LOGIN = 400
HEIGHT_LOGIN = 600
WIDTH_SYNC = 1200
HEIGHT_SYNC = 700

import os
from kivy.config import Config
Config.set('kivy', 'desktop', 1)
# disable multitouch emulation with mouse's clicks
Config.set('input', 'mouse', 'mouse,disable_multitouch')
from .utils_kivy import get_icon_path
Config.set('kivy', 'window_icon', get_icon_path())
Config.write()

# Kivy's import must happen after the configuration
import kivy
kivy.require('1.7.2')

from functools import partial
import anydbm
import platform
import shelve
import traceback
import webbrowser

from kivy.app import App
from kivy.base import stopTouchApp
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, TransitionBase
import pygame

from . import __version__ as current_version
from .client import Client
from .utils_kivy import (
    ConfirmDialog,
    DirChooserDialog,
    EmptyScreen,
    HOME_DIR,
    InfoDialog,
    LinkButton,
    LoadSitesListThread,
    LoadingDialog,
    LoginScreen,
    LoginThread,
    SyncDirThread,
    SyncScreen,
    WebsitesManager,
    notify,
)

KNOWN_CONFIG_FILES_FILTERS = ['*.yaml', '*.py']
LAST_DIR_KEY = 'last_dir'
SITES_DATABASE_FILENAME = 'sites_database'
USER_SETTINGS_SECTION = 'user_settings'
WINDOW_TITLE = 'Aldryn App'

# window resizing parameters
RESIZING_DURATION = 0.0
RESIZING_EASING = 7
RESIZING_STEPS = 1

# urls
ACCOUNT_CREATION_URL = 'https://login.django-cms.com/login/'
TROUBLE_SIGNING_IN_URL = 'https://login.django-cms.com/account/reset-password/'
CONTROL_PANEL_URL = 'https://control.django-cms.com/control/'
ADD_NEW_SITE_URL = 'https://control.django-cms.com/control/new/'


####################
# App's main class #
####################

class AldrynGUIApp(App):

    title = WINDOW_TITLE
    icon = get_icon_path()

    def __init__(self, *args, **kwargs):
        super(AldrynGUIApp, self).__init__(*args, **kwargs)
        self.client = Client(
            os.environ.get(Client.ALDRYN_HOST_KEY, Client.ALDRYN_HOST_DEFAULT),
            interactive=False)
        sites_dir_database_file_path = os.path.join(self.user_data_dir, SITES_DATABASE_FILENAME)

        def open_db():
            self.sites_dir_database = shelve.open(sites_dir_database_file_path, writeback=True)
        try:
            open_db()
        except anydbm.error:  # "db type could not be determined"
            traceback.print_exc()  # log the exception
            os.remove(sites_dir_database_file_path)  # remove corrupted db file
            open_db()  # retry

    def build_config(self, config):
        config.setdefaults(USER_SETTINGS_SECTION, {
            LAST_DIR_KEY: HOME_DIR
        })

    def build(self):
        sm = ScreenManager(transition=TransitionBase(duration=0.1))
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(SyncScreen(name='sync'))
        sm.add_widget(EmptyScreen(name='empty'))
        return sm

    def on_key_down(self, win, key, scancode, string, modifiers):
        system = platform.system()
        if system == 'Darwin':
            if 'meta' in modifiers:
                if key == 113:  # cmd+q
                    stopTouchApp()
                    return True
                if key == 104:  # cmd+h
                    pygame.display.iconify()
                    return True
        elif platform == 'Windows':
            if 'alt' in modifiers and key == 285:  # alt+f4
                stopTouchApp()
                return True

    def on_start(self):
        super(AldrynGUIApp, self).on_start()

        Window.bind(on_key_down=self.on_key_down)

        sites_list_view = self._get_sites_list_view()
        self._websites_manager = WebsitesManager(self.sites_dir_database, sites_list_view)

        if self.client.is_logged_in():
            self.set_screen_to_sync()
        else:
            self.set_screen_to_login()

    def on_stop(self):
        self.sites_dir_database.close()
        self.config.write()
        self._websites_manager.stop_all_threads()
        super(AldrynGUIApp, self).on_stop()

    def set_screen_to_sync(self):
        Window.size = WIDTH_SYNC, HEIGHT_SYNC
        self.root.current = 'sync'
        self.load_sites_list()

    def set_screen_to_login(self):
        Window.size = WIDTH_LOGIN, HEIGHT_LOGIN
        self.root.current = 'login'

    ### DIALOGS ###

    def show_info_dialog(self, title, msg, on_open=None):
        info_popup = None

        def dismiss_info_dialog():
            if info_popup and hasattr(info_popup, 'dismiss'):
                info_popup.dismiss()

        content = InfoDialog(close=dismiss_info_dialog)
        content.message_label.text = msg
        info_popup = Popup(
            title=title, content=content, auto_dismiss=False,
            size_hint=(0.9, None), height=200)
        if on_open:
            info_popup.on_open = on_open
        info_popup.open()
        return info_popup

    def show_confirm_dialog(self, title, msg, on_confirm, on_cancel=None,
                            cancel_btn_text='Cancel',
                            confirm_btn_text='Confirm',
                            on_open=None):
        confirm_popup = None

        def dismiss_confirm_dialog():
            if confirm_popup and hasattr(confirm_popup, 'dismiss'):
                confirm_popup.dismiss()

        def on_confirm_wrapper():
            dismiss_confirm_dialog()
            on_confirm()

        def on_cancel_wrapper():
            dismiss_confirm_dialog()
            if callable(on_cancel):
                on_cancel()

        content = ConfirmDialog(confirm_callback=on_confirm_wrapper,
                                cancel_callback=on_cancel_wrapper,
                                cancel_btn_text=cancel_btn_text,
                                confirm_btn_text=confirm_btn_text)
        content.message_label.text = msg
        confirm_popup = Popup(
            title=title, content=content,
            auto_dismiss=False, size_hint=(0.9, None), height=200)
        if on_open:
            confirm_popup.on_open = on_open
        confirm_popup.open()
        return confirm_popup

    def show_loading_dialog(self, on_open=None):
        content = LoadingDialog()
        loading_popup = Popup(
            title='', auto_dismiss=False, content=content,
            size_hint=(0.9, None), height=200)
        if on_open:
            loading_popup.on_open = on_open
        loading_popup.open()
        return loading_popup

    def show_dir_chooser_dialog(self, on_selection, path=None, on_open=None):
        dir_chooser_popup = None

        def dismiss_dir_chooser_dialog():
            if dir_chooser_popup and hasattr(dir_chooser_popup, 'dismiss'):
                dir_chooser_popup.dismiss()

        def on_selection_wrapper(path, selection, new_dir_name):
            dir_path = path
            if new_dir_name:
                dir_path = os.path.join(path, new_dir_name)
                try:
                    os.mkdir(dir_path)
                except OSError as e:
                    if e.errno == 17:  # File exists
                        msg = 'Directory "%s" already exists' % new_dir_name
                    else:
                        msg = 'Invalid filename'
                    self.show_info_dialog('Error', msg)
                    return
            elif selection:
                if selection[0].startswith('..'):  # disallow selection of the parent directory
                    return
                else:
                    dir_path = selection[0]
            dismiss_dir_chooser_dialog()
            on_selection(dir_path)

        content = DirChooserDialog(
            select=on_selection_wrapper, cancel=dismiss_dir_chooser_dialog)
        file_chooser = content.file_chooser
        file_chooser.path = path or self._get_last_dir()
        file_chooser.bind(path=lambda instance, path: self._set_last_dir(path))
        dir_chooser_popup = Popup(
            title="Choose directory", content=content, size_hint=(0.9, 0.9))
        if on_open:
            dir_chooser_popup.on_open = on_open
        dir_chooser_popup.open()
        return dir_chooser_popup

    ### END OF DIALOGS ###

    def _resize_window(self, target_width, target_height, callback=None):
        current_width, current_height = Window.size
        step_duration = RESIZING_DURATION / RESIZING_STEPS

        def set_size(steps_left, dt):
            steps_left = steps_left - 1 if steps_left > 0 else 0
            ratio = steps_left * 1.0 / RESIZING_STEPS
            ratio **= RESIZING_EASING
            width = int(current_width * ratio + target_width * (1.0 - ratio))
            height = int(current_height * ratio + target_height * (1.0 - ratio))
            Window.size = width, height
            if steps_left > 0:
                Clock.schedule_once(partial(set_size, steps_left), step_duration)
            elif callback:
                callback()

        set_size(RESIZING_STEPS, 0.0)

    def login(self, email, password):
        loading_dialog = self.show_loading_dialog()
        login_callback = partial(self._login_callback, loading_dialog)
        self._login_thread = LoginThread(
            email, password, self.client, login_callback)
        self._login_thread.start()

    def _login_callback(self, loading_dialog, status, msg):
        loading_dialog.dismiss()
        if status:

            def callback():  # change screen to sync after the animation
                self.root.get_screen('sync').on_enter = self.load_sites_list
                self.root.current = 'sync'
            # start the animation after the empty screen is loaded
            animate_window_resize = partial(self._resize_window, WIDTH_SYNC, HEIGHT_SYNC, callback=callback)
            self.root.get_screen('empty').on_enter = animate_window_resize
            self.root.current = 'empty'
        else:
            self.show_info_dialog('Error', msg)

    def logout(self):
        self.client.logout()
        self._websites_manager.clear_websites()

        def callback():  # change screen from empty to sync after the animation
            self.root.current = 'login'
        # start the animation after the empty screen is loaded
        animate_window_resize = partial(self._resize_window, WIDTH_LOGIN, HEIGHT_LOGIN, callback=callback)
        self.root.get_screen('empty').on_enter = animate_window_resize
        self.root.current = 'empty'

    def _get_sites_list_view(self):
        return self.root.get_screen('sync').sites_list_view

    def load_sites_list(self):
        loading_dialog = self.show_loading_dialog()
        load_sites_list_callback = partial(
            self._load_sites_list_callback, loading_dialog)
        self._load_sites_list_thread = LoadSitesListThread(
            self.client, load_sites_list_callback)
        self._load_sites_list_thread.start()

    def _load_sites_list_callback(self, loading_dialog, status, data, version_data=None):
        loading_dialog.dismiss()
        if status:
            new_sites_names = set()
            old_sites_names = set(self._websites_manager.get_domains())
            for site_data in data:
                domain = site_data['domain'].encode('utf-8')
                new_sites_names.add(domain)
                self._websites_manager.add_or_update_website(
                    domain, site_data)
            removed_sites_names = old_sites_names - new_sites_names
            for removed_domain in removed_sites_names:
                self._websites_manager.remove_website(removed_domain)

            if version_data:
                newest_version = version_data['version']
                if newest_version > current_version:
                    system = platform.system()
                    if system == 'Darwin':
                        link = version_data['osx_link']
                    elif system == 'Windows':
                        link = version_data['windows_link']
                    else:
                        link = None
                    if link:
                        sync_screen = self.root.get_screen('sync')
                        if hasattr(sync_screen, 'newest_version_btn'):
                            newest_version_btn = sync_screen.newest_version_btn
                        else:
                            newest_version_btn = LinkButton()
                            sync_screen.newest_version_btn = newest_version_btn
                            sync_screen.top_right_buttons.add_widget(newest_version_btn)
                        newest_version_btn.text = 'Newer version is available (%s => %s)' % (current_version, newest_version)
                        newest_version_btn.bind(on_release=lambda *args: webbrowser.open(link))

        else:
            msg = unicode(data)
            self.show_info_dialog('Error', msg)

    def select_site_dir(self, domain, on_selection=None):

        def on_selection_wrapper(site_dir):
            self._select_site_dir_callback(domain, site_dir)
            if callable(on_selection):
                on_selection()
        site_dir = self._websites_manager.get_site_dir(domain)
        self.show_dir_chooser_dialog(on_selection_wrapper, path=site_dir)

    def _select_site_dir_callback(self, domain, site_dir):
        self._websites_manager.set_site_dir(domain, site_dir)

    ### SYNC ###

    def sync_toggle(self, domain):
        handler = self._websites_manager.get_site_sync_handler(domain)
        if handler:
            self.stop_sync(domain)
        else:
            site_dir = self._websites_manager.get_site_dir(domain)
            if site_dir:
                # XXX since git sync solution we don't discard any local changes
                #on_confirm = partial(self._sync_confirmed, domain, site_dir)
                #title = 'Confirm sync'
                #name = self._websites_manager.get_site_name(domain)
                #msg = 'All local changes to the boilerplate of "%s" will be undone. Continue?' % name
                #self.show_confirm_dialog(title, msg, on_confirm)
                self._sync_confirmed(domain, site_dir)
            else:
                self.select_site_dir(domain, on_selection=lambda *args: self.sync_toggle(domain))

    def stop_sync(self, domain):
        self._websites_manager.stop_site_sync_handler(domain)

    def _sync_confirmed(self, domain, site_dir, force=False):
        loading_dialog = self.show_loading_dialog()
        path = site_dir.encode('utf-8')
        sync_callback = partial(self._sync_callback, loading_dialog)
        stop_sync_callback = partial(self._stop_sync_callback, domain)

        def network_error_callback(message, on_confirm, on_cancel):
            def on_cancel_wrapper():
                self.stop_sync(domain)
                on_cancel()
            self.show_confirm_dialog(
                'Network error', message,
                on_confirm, on_cancel=on_cancel_wrapper,
                confirm_btn_text='Retry',
                cancel_btn_text='Stop sync (lose unsynced changes!)')

        def sync_error_callback(message, title='Error'):
            notify(WINDOW_TITLE, message)
            self.show_info_dialog(title, message)

        def protected_file_change_callback(message):
            notify(WINDOW_TITLE, message)
            self.show_info_dialog('Info', message)

        def sync_indicator_callback(stop=False):
            if stop:
                self._websites_manager.hide_sync_loading_overlay(domain)
            else:
                self._websites_manager.show_sync_loading_overlay(domain)

        sync_dir_thread = SyncDirThread(
            domain, path, force, self.client,
            sync_callback,
            sync_indicator_callback,
            stop_sync_callback,
            network_error_callback,
            sync_error_callback,
            protected_file_change_callback)
        sync_dir_thread.start()

    def _sync_callback(self, loading_dialog, domain, status, msg_or_sync_handler):
        loading_dialog.dismiss()
        if status:  # handler
            self._websites_manager.set_site_sync_handler(domain, msg_or_sync_handler)
        else:  # msg
            if msg_or_sync_handler == Client.DIRECTORY_ALREADY_SYNCING_MESSAGE:
                site_dir = self._websites_manager.get_site_dir(domain)
                if site_dir:
                    on_confirm = partial(
                        self._sync_confirmed, domain, site_dir, force=True)
                    self.show_confirm_dialog(
                        'Directory already syncing',
                        'It seems that you are already syncing this directory',
                        on_confirm,
                        cancel_btn_text='Cancel',
                        confirm_btn_text='Continue anyway')
                else:
                    self.select_site_dir(domain)
            else:
                self.show_info_dialog('Error', msg_or_sync_handler)

    def _stop_sync_callback(self, domain, msg):
        handler = self._websites_manager.get_site_sync_handler(domain)
        if handler:
            if hasattr(handler, '_continue_despite_stop_callback'):
                return
            else:
                handler._continue_despite_stop_callback = True
        notify(WINDOW_TITLE, msg)
        on_confirm = partial(self.stop_sync, domain)
        title = 'Stop syncing'
        cancel_btn_text = 'No, continue'
        confirm_btn_text = 'Yes, stop syncing'
        self.show_confirm_dialog(title, msg, on_confirm,
                                 cancel_btn_text=cancel_btn_text,
                                 confirm_btn_text=confirm_btn_text)

    ### END OF SYNC ###

    def _set_last_dir(self, path):
        self.config.set(USER_SETTINGS_SECTION, LAST_DIR_KEY, path)
        self.config.write()

    def _get_last_dir(self):
        return self.config.getdefault(USER_SETTINGS_SECTION, LAST_DIR_KEY, HOME_DIR)

    def browser_open_account_creation(self):
        webbrowser.open(ACCOUNT_CREATION_URL)

    def browser_open_trouble_signing_in(self):
        webbrowser.open(TROUBLE_SIGNING_IN_URL)

    def browser_open_control_panel(self):
        webbrowser.open(CONTROL_PANEL_URL)

    def browser_open_add_new_site(self):
        webbrowser.open(ADD_NEW_SITE_URL)

    def browser_open_site_dashboard(self, domain):
        webbrowser.open(self._websites_manager.get_site_dashboard_url(domain) or
                        CONTROL_PANEL_URL)

    def browser_open_stage(self, domain):
        webbrowser.open(self._websites_manager.get_site_stage_url(domain) or
                        CONTROL_PANEL_URL)


if __name__ == '__main__':
    AldrynGUIApp().run()
