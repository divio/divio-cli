# -*- coding: utf-8 -*-
# Configuring kivy
import kivy
kivy.require('1.7.2')

# window size's and position
WIDTH_LOGIN = 400
HEIGHT_LOGIN = 600
WIDTH_SYNC = 1200
HEIGHT_SYNC = 700
POSITION_TOP = 200
POSITION_LEFT = 200

from kivy.config import Config
Config.set('kivy', 'desktop', 1)
# app's default window's position
#Config.set('graphics', 'position', 'custom')
#Config.set('graphics', 'top', POSITION_TOP)
#Config.set('graphics', 'left', POSITION_LEFT)


from functools import partial
import os
import shelve
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.screenmanager import Screen, ScreenManager, TransitionBase

from client import Client
from utils_kivy import TabTextInput

HOME_DIR = os.path.expanduser('~')
KNOWN_CONFIG_FILES_FILTERS = ['*.yaml', '*.py']
SITES_DATABASE_FILENAME = 'sites_database'
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

    def __init__(self, *args, **kwargs):
        super(LoginScreen, self).__init__(*args, **kwargs)


class EmptyScreen(BaseScreen):
    pass


class SyncScreen(BaseScreen):
    sites_list_view = ObjectProperty(None)


###########
# Dialogs #
###########

class InfoDialog(BoxLayout):
    close = ObjectProperty(None)
    message_label = ObjectProperty(None)


class LoadingDialog(BoxLayout):
    pass


class ConfirmDialog(BoxLayout):
    pass


class DirChooserDialog(BoxLayout):
    cancel = ObjectProperty(None)
    select = ObjectProperty(None)


##################
# Custom widgets #
##################

class Website(RelativeLayout):
    name_label = ObjectProperty(None)
    dir_label = ObjectProperty(None)
    change_or_set_dir_btn = ObjectProperty(None)
    sync_btn = ObjectProperty(None)


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
        status, data = self.client.sites(interactive=False)
        Clock.schedule_once(lambda dt: self.callback(status, data), 0)


#############
# App class #
#############

class CMSCloudGUIApp(App):

    title = WINDOW_TITLE

    def __init__(self, *args, **kwargs):
        super(CMSCloudGUIApp, self).__init__(*args, **kwargs)
        self.client = Client(os.environ.get(Client.CMSCLOUD_HOST_KEY, Client.CMSCLOUD_HOST_DEFAULT))
        sites_database_file_path = os.path.join(self.user_data_dir, SITES_DATABASE_FILENAME)
        self.sites_database = shelve.open(sites_database_file_path, writeback=True)

        self.site_views_cache = {}
        self.site_sync_threads = {}

    def _clear_data(self):
        sites_list_view = self._get_sites_list_view()
        for view in self.site_views_cache.values():
            sites_list_view.remove_widget(view)
        self.site_views_cache = {}

        for t in self.site_sync_threads.values():
            t.stop()
            t.join()
        self.site_sync_threads = {}

    def build(self):
        sm = ScreenManager(transition=TransitionBase(duration=0.1))
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(SyncScreen(name='sync'))
        sm.add_widget(EmptyScreen(name='empty'))
        return sm

    def on_start(self):
        super(CMSCloudGUIApp, self).on_start()
        if self.client.is_logged_in():
            self.set_screen_to_sync()
        else:
            self.set_screen_to_login()

    def on_stop(self):
        self.sites_database.close()
        super(CMSCloudGUIApp, self).on_stop()

    def set_screen_to_sync(self):
        Window.size = WIDTH_SYNC, HEIGHT_SYNC
        self.root.current = 'sync'
        self.load_sites_list()

    def set_screen_to_login(self):
        Window.size = WIDTH_LOGIN, HEIGHT_LOGIN
        self.root.current = 'login'

    def dismiss_info_dialog(self):
        if hasattr(self, '_info_popup') and self._info_popup:
            self._info_popup.dismiss()
            del self._info_popup

    def show_info_dialog(self, title, msg, on_open=None):
        content = InfoDialog(close=self.dismiss_info_dialog)
        content.message_label.text = msg
        self._info_popup = Popup(title=title, content=content, size_hint=(0.9, None), height=200)
        if on_open:
            self._info_popup.on_open = on_open
        self._info_popup.open()

    def dismiss_loading_dialog(self):
        if hasattr(self, '_loading_popup') and self._loading_popup:
            self._loading_popup.dismiss()
            del self._loading_popup

    def show_loading_dialog(self, on_open=None):
        content = LoadingDialog(close=self.dismiss_loading_dialog)
        self._loading_popup = Popup(title='', auto_dismiss=False, content=content, size_hint=(0.9, None), height=200)
        if on_open:
            self._loading_popup.on_open = on_open
        self._loading_popup.open()

    def dismiss_dir_chooser_dialog(self):
        if hasattr(self, '_dir_chooser_popup') and self._dir_chooser_popup:
            self._dir_chooser_popup.dismiss()
            del self._dir_chooser_popup

    def show_dir_chooser_dialog(self, on_selection, on_open=None):
        content = DirChooserDialog(select=on_selection, cancel=self.dismiss_dir_chooser_dialog)
        self._dir_chooser_popup = Popup(title="Choose directory", content=content, size_hint=(0.9, 0.9))
        if on_open:
            self._dir_chooser_popup.on_open = on_open
        self._dir_chooser_popup.open()

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
        self.show_loading_dialog()
        self._login_thread = LoginThread(email, password, self.client, self._login_callback)
        self._login_thread.start()

    def _login_callback(self, status, msg):
        self.dismiss_loading_dialog()
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
        self.client.logout(interactive=False)
        self._clear_data()

        def callback():  # change screen from empty to sync after the animation
            self.root.current = 'login'
        # start the animation after the empty screen is loaded
        animate_window_resize = partial(self._resize_window, WIDTH_LOGIN, HEIGHT_LOGIN, callback=callback)
        self.root.get_screen('empty').on_enter = animate_window_resize
        self.root.current = 'empty'

    def _get_sites_list_view(self):
        return self.root.get_screen('sync').sites_list_view

    def load_sites_list(self):
        self.show_loading_dialog()
        self._load_sites_list_thread = LoadSitesListThread(self.client, self._load_sites_list_callback)
        self._load_sites_list_thread.start()

    def _load_sites_list_callback(self, status, data):
        self.dismiss_loading_dialog()
        if status:
            sites_list_view = self._get_sites_list_view()
            for site_data in data:
                name = site_data['name'].encode('utf-8')

                site_view = None
                if name in self.site_views_cache:
                    site_view = self.site_views_cache[name]
                else:
                    site_view = Website()
                    site_view.name_label.text = name

                site_dir = None
                if name in self.sites_database:
                    d = self.sites_database[name]
                    site_dir = d.get('dir', '')
                else:
                    self.sites_database[name] = site_data
                if site_dir:
                    site_view.dir_label.text = site_dir
                    site_view.change_or_set_dir_btn.text = 'change'
                else:
                    site_view.change_or_set_dir_btn.text = 'Set sync destination folder'

                if name in self.site_sync_threads:
                    site_view.sync_btn.text = 'Stop Sync'
                else:
                    site_view.sync_btn.text = 'Sync Files'

                if name not in self.site_views_cache:
                    sites_list_view.add_widget(site_view)
                    self.site_views_cache[name] = site_view
        else:
            msg = unicode(data)
            self.show_info_dialog('Error', msg)

    def set_site_dir(self, site_name):
        on_selection = partial(self._set_site_dir_callback, site_name)
        self.show_dir_chooser_dialog(on_selection)

    def _set_site_dir_callback(self, site_name, path, selection):
        self.dismiss_dir_chooser_dialog()
        if selection:
            site_dir = selection[0]
        else:
            site_dir = path
        self.sites_database[site_name]['dir'] = site_dir
        self.sites_database.sync()
        site_view = self.site_views_cache[site_name]
        site_view.dir_label.text = site_dir
        site_view.change_or_set_dir_btn.text = 'change'

    def sync(self, sync_btn, site_name):
        observer = self.site_sync_threads.get(site_name, None)
        if observer:
            observer.stop()
            observer.join()
            del self.site_sync_threads[site_name]
            sync_btn.text = 'Sync Files'
        else:
            site_dir = self.sites_database[site_name].get('dir', None)
            if site_dir:
                # TODO confirmation
                path = site_dir.encode('utf-8')  # otherwise watchdog's observer crashed
                sitename = self.sites_database[site_name]['domain'].encode('utf-8')
                try:
                    status, msg_or_observer = self.client.sync(sitename=sitename, path=path, interactive=False)
                except OSError as e:
                    self.show_info_dialog('Filesystem Error', str(e))
                else:
                    if status:  # observer
                        self.site_sync_threads[site_name] = msg_or_observer
                        sync_btn.text = 'Stop Sync'
                    else:  # msg
                        self.show_info_dialog('Error', msg_or_observer)
            else:
                self.set_site_dir(site_name)

    def browser_open_account_creation(self):
        webbrowser.open(ACCOUNT_CREATION_URL)

    def browser_open_trouble_signing_in(self):
        webbrowser.open(TROUBLE_SIGNING_IN_URL)

    def browser_open_control_panel(self):
        webbrowser.open(CONTROL_PANEL_URL)

    def browser_open_add_new_site(self):
        webbrowser.open(ADD_NEW_SITE_URL)


if __name__ == '__main__':
    CMSCloudGUIApp().run()
