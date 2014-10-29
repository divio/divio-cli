# -*- coding: utf-8 -*-
import os
import platform
import subprocess
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.logger import Logger
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.image import Image
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.utils import get_color_from_hex
from plyer import notification

from .utils import resource_path, get_icon_path

HOME_DIR = os.path.expanduser('~')
# status to dot color mapping
STATUS_TO_COLOR = {
    0: get_color_from_hex('#4a9cf2'),  # NEW, blue
    1: get_color_from_hex('#98ba0f'),  # DEPLOYED, green
    2: get_color_from_hex('#4a9cf2'),  # DEPLOYING, blue
    3: get_color_from_hex('#626262'),  # OFFLINE, grey
    4: get_color_from_hex('#f0453b'),  # ERROR, red
}


###########
# Dialogs #
###########

class InfoDialog(BoxLayout):
    close = ObjectProperty(None)
    message_label = ObjectProperty(None)


class ConfirmDialog(BoxLayout):
    cancel_callback = ObjectProperty(None)
    confirm_callback = ObjectProperty(None)
    message_label = ObjectProperty(None)
    cancel_btn_text = ObjectProperty(None)
    confirm_btn_text = ObjectProperty(None)


class LoadingDialog(RelativeLayout):
    message_label = ObjectProperty(None)


class DirChooserDialog(BoxLayout):
    cancel = ObjectProperty(None)
    file_chooser = ObjectProperty(None)
    select = ObjectProperty(None)


##################
# Custom widgets #
##################

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


class LoadingImage(Image):
    loader_img = resource_path('img/loader.gif')


class PaddedButton(Button):
    pass


class LinkButton(PaddedButton):
    pass


class OpenButton(Button):
    external_img = resource_path('img/external.png')


class CustomFileChooserListView(FileChooserListView):

    def __init__(self, *args, **kwargs):
        super(CustomFileChooserListView, self).__init__(*args, **kwargs)
        self.bind(path=self._normalize_path)

    def _normalize_path(self, *args, **kwargs):
        norm_path = os.path.normpath(self.path)
        if norm_path != self.path:
            self.path = norm_path

    def go_to_home_dir(self):
        self.path = HOME_DIR


class WebsiteView(RelativeLayout):
    status_btn = ObjectProperty(None)
    name_btn = ObjectProperty(None)
    dir_label = ObjectProperty(None)
    change_or_set_dir_btn = ObjectProperty(None)
    open_dir_btn = ObjectProperty(None)
    preview_btn = ObjectProperty(None)
    sync_btn = ObjectProperty(None)
    sync_loading_overlay = ObjectProperty(None)

    domain = StringProperty(None)

    def __init__(self, domain):
        super(WebsiteView, self).__init__()
        self.domain = domain
        self.hide_sync_loading_overlay()

    def set_name(self, name):
        self.name_btn.text = name

    def set_status_color(self, color):
        self.status_btn.color = color

    def _set_dir_btn_text_to_change(self):
        self.change_or_set_dir_btn.text = 'change'

    def _set_dir_btn_text_to_set(self):
        self.change_or_set_dir_btn.text = 'Set sync destination folder'

    def set_site_dir_widgets(self, site_dir):
        if site_dir:
            self.dir_label.text = site_dir
            self._set_dir_btn_text_to_change()
            if not self.open_dir_btn:
                open_dir_btn = OpenButton()
                self.change_or_set_dir_btn.parent.add_widget(open_dir_btn)
                self.open_dir_btn = open_dir_btn
            self.open_dir_btn.on_release = lambda: open_in_file_manager(site_dir)
        else:
            self._set_dir_btn_text_to_set()

    def set_sync_btn_text_to_stop(self):
        if not hasattr(self, '_background_color_orig'):
            self._background_color_orig = self.sync_btn.background_color
        if not hasattr(self, '_background_down_orig'):
            self._background_down_orig = self.sync_btn.background_down
        if not hasattr(self, '_background_normal_orig'):
            self._background_normal_orig = self.sync_btn.background_normal

        self.sync_btn.background_color = (0.33, 0.66, 0.9, 1)
        self.sync_btn.background_down = ''
        self.sync_btn.background_normal = ''
        self.sync_btn.text = 'Stop Sync'

    def set_sync_btn_text_to_sync(self):
        if hasattr(self, '_background_color_orig'):
            self.sync_btn.background_color = self._background_color_orig
        if hasattr(self, '_background_down_orig'):
            self.sync_btn.background_down = self._background_down_orig
        if hasattr(self, '_background_normal_orig'):
            self.sync_btn.background_normal = self._background_normal_orig

        self.sync_btn.text = 'Sync Files'

    def show_sync_loading_overlay(self):
        if self.sync_loading_overlay.parent is None:
            self.sync_btn.add_widget(self.sync_loading_overlay)

    def hide_sync_loading_overlay(self):
        if self.sync_loading_overlay.parent is not None:
            self.sync_btn.remove_widget(self.sync_loading_overlay)


######################
# Asynchronous tasks #
######################

class LoginThread(threading.Thread):

    def __init__(self, email, password, client, callback):
        super(LoginThread, self).__init__()
        self.email = email
        self.password = password
        self.client = client
        self.callback = callback

    def run(self):
        status, msg = self.client.login(email=self.email, password=self.password)
        Clock.schedule_once(lambda dt: self.callback(status, msg), 0)


class LoadSitesListThread(threading.Thread):

    def __init__(self, client, callback):
        super(LoadSitesListThread, self).__init__()
        self.client = client
        self.callback = callback

    def run(self):
        status, data = self.client.sites()
        # Also retrieving the latest version number
        version_data = None
        if status:
            version_status, version_data = self.client.newest_version()
            if not version_status:
                version_data = None
        Clock.schedule_once(lambda dt: self.callback(status, data, version_data=version_data), 0)


class SyncDirThread(threading.Thread):

    def __init__(self, domain, path, force, client,
                 sync_callback, sync_indicator_callback, stop_sync_callback,
                 network_error_callback, sync_error_callback,
                 protected_file_change_callback):
        super(SyncDirThread, self).__init__()
        self.domain = domain
        self.path = path
        self.force = force
        self.client = client
        self.sync_callback = sync_callback
        self.sync_indicator_callback = sync_indicator_callback
        self.stop_sync_callback = stop_sync_callback
        self.network_error_callback = network_error_callback
        self.sync_error_callback = sync_error_callback
        self.protected_file_change_callback = protected_file_change_callback

    def run(self):
        app = App.get_running_app()
        domain = app.sites_dir_database[self.domain]['domain'].encode('utf-8')
        try:
            status, msg_or_sync_handler = self.client.sync(
                self.network_error_callback, self.sync_error_callback,
                self.protected_file_change_callback, sitename=domain,
                path=self.path, force=self.force,
                sync_indicator_callback=self.sync_indicator_callback,
                stop_sync_callback=self.stop_sync_callback)
        except OSError as e:
            Clock.schedule_once(
                lambda dt: app.show_info_dialog('Filesystem Error', str(e)), 0)
        else:
            Clock.schedule_once(
                lambda dt: self.sync_callback(
                    self.domain, status, msg_or_sync_handler), 0)


###########
# Helpers #
###########

class WebsitesManager(object):

    def __init__(self, sites_dir_database, sites_list_view):
        self._sites_dir_database = sites_dir_database
        self._sites_list_view = sites_list_view
        self._site_views_cache = {}
        self._site_sync_handlers = {}

    def add_or_update_website(self, domain, site_data):
        site_view = None
        if domain in self._site_views_cache:
            site_view = self._site_views_cache[domain]
        else:
            site_view = WebsiteView(domain)

        name = site_data['name'].encode('utf-8')
        site_view.set_name(name)

        stage_status = site_data['stage_status']
        site_view.set_status_color(STATUS_TO_COLOR[stage_status])

        site_dir = None
        if domain in self._sites_dir_database:
            site_dir = self.get_site_dir(domain)
        else:
            self._sites_dir_database[domain] = {}
        self._sites_dir_database[domain].update(site_data)

        site_view.set_site_dir_widgets(site_dir)

        if domain in self._site_sync_handlers:
            site_view.set_sync_btn_text_to_stop()
        else:
            site_view.set_sync_btn_text_to_sync()

        if domain not in self._site_views_cache:
            self._sites_list_view.add_widget(site_view)
            self._site_views_cache[domain] = site_view

    def remove_website(self, domain):
        site_view = self._site_views_cache[domain]
        self._sites_list_view.remove_widget(site_view)
        del self._site_views_cache[domain]

        if domain in self._site_sync_handlers:
            site_sync_thread = self._site_sync_handlers[domain]
            site_sync_thread.stop()
            del self._site_sync_handlers[domain]

    def clear_websites(self):
        self._sites_list_view.clear_widgets()
        self._site_views_cache.clear()

        self.stop_all_threads()

    def stop_all_threads(self):
        for handler in self._site_sync_handlers.values():
            handler.stop()
        self._site_sync_handlers.clear()

    def get_site_name(self, domain):
        return self._sites_dir_database[domain]['name'].encode('utf-8')

    def get_domains(self):
        return self._site_views_cache.keys()

    def get_site_dashboard_url(self, domain):
        return self._sites_dir_database[domain].get(
            'dashboard_url', None)

    def get_site_stage_url(self, domain):
        return self._sites_dir_database[domain].get(
            'stage_url', None)

    ### Site's sync handler ###

    def _delete_site_sync_handler(self, domain):
        handler = self.get_site_sync_handler(domain)
        if handler:
            handler.stop()
            del self._site_sync_handlers[domain]
            site_view = self._site_views_cache[domain]
            site_view.set_sync_btn_text_to_sync()

    def set_site_sync_handler(self, domain, handler):
        # stopping and removing any older syncing handler
        self._delete_site_sync_handler(domain)

        self._site_sync_handlers[domain] = handler
        site_view = self._site_views_cache[domain]
        site_view.set_sync_btn_text_to_stop()

    def get_site_sync_handler(self, domain):
        return self._site_sync_handlers.get(domain, None)

    def stop_site_sync_handler(self, domain):
        self._delete_site_sync_handler(domain)
        self.hide_sync_loading_overlay(domain)

    def show_sync_loading_overlay(self, domain):
        self._site_views_cache[domain].show_sync_loading_overlay()

    def hide_sync_loading_overlay(self, domain):
        self._site_views_cache[domain].hide_sync_loading_overlay()

    ### Site's sync directory ###

    def get_site_dir(self, domain):
        return self._sites_dir_database[domain].get('dir', None)

    def set_site_dir(self, domain, site_dir):
        self._sites_dir_database[domain]['dir'] = site_dir
        self._sites_dir_database.sync()
        site_view = self._site_views_cache[domain]
        site_view.set_site_dir_widgets(site_dir)


################
# Main widgets #
################

class BaseScreen(Screen):
    pass


class LoginScreen(BaseScreen):
    login_btn = ObjectProperty(None)
    trouble_btn = ObjectProperty(None)
    create_aldryn_id_btn = ObjectProperty(None)
    email = TabTextInput()
    password = TabTextInput()

    aldryn_logo_white_img = resource_path('img/aldryn_logo_white.png')

    def __init__(self, *args, **kwargs):
        super(LoginScreen, self).__init__(*args, **kwargs)


class EmptyScreen(BaseScreen):
    aldryn_logo_img = resource_path('img/aldryn_logo.png')


class SyncScreen(BaseScreen):
    sites_list_view = ObjectProperty(None)

    aldryn_logo_img = resource_path('img/aldryn_logo.png')


##################
# OS integration #
##################

system = platform.system()


def open_in_file_manager(path):
    if system == 'Windows':
        subprocess.Popen(['start', path], shell=True)
    elif system == 'Darwin':
        subprocess.Popen(['open', path])
    else:
        try:
            subprocess.Popen(['xdg-open', path])
        except OSError:
            Logger.exception('Cannot open external file manager')


def notify(title, message, bring_up=False):
    try:
        kwargs = {'title': title, 'message': message}
        if system == "Windows" or system == "Linux":
            kwargs['app_icon'] = os.path.abspath(get_icon_path())
            kwargs['timeout'] = 4
        notification.notify(**kwargs)
        if system == 'Darwin':
            from AppKit import NSApp, NSApplication
            NSApplication.sharedApplication()
            app = NSApp()
            app.requestUserAttention_(0)  # this should bounce the icon
            # the 0 should be replaced by the NSRequestUserAttentionType.NSCriticalRequest
            # imported from NSApplication? TODO
            # https://developer.apple.com/library/mac/documentation/Cocoa/Reference/ApplicationKit/Classes/NSApplication_Class/Reference/Reference.html#//apple_ref/doc/c_ref/NSRequestUserAttentionType
            if bring_up:
                app.activateIgnoringOtherApps_(True)  # this should bring the app to the foreground
    except Exception as e:
        print e
        Logger.exception('Notification error:\n%s' % e)

