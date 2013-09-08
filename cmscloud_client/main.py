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
Config.set('input', 'mouse', 'mouse,disable_multitouch')
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
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.screenmanager import Screen, ScreenManager, TransitionBase

from client import Client
from http_server import get_static_server
from utils_kivy import TabTextInput, open_in_file_manager

HOME_DIR = os.path.expanduser('~')
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

# localhost static server
STATIC_SERVER_PORT = 59687


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


class ConfirmDialog(BoxLayout):
    cancel = ObjectProperty(None)
    confirm = ObjectProperty(None)
    message_label = ObjectProperty(None)


class LoadingDialog(RelativeLayout):
    pass


class DirChooserDialog(BoxLayout):
    cancel = ObjectProperty(None)
    file_chooser = ObjectProperty(None)
    select = ObjectProperty(None)


##################
# Custom widgets #
##################

class PaddedButton(Button):
    pass


class LinkButton(PaddedButton):
    pass


class OpenButton(Button):
    pass


class WebsiteView(RelativeLayout):
    name_btn = ObjectProperty(None)
    dir_label = ObjectProperty(None)
    change_or_set_dir_btn = ObjectProperty(None)
    open_dir_btn = ObjectProperty(None)
    sync_btn = ObjectProperty(None)

    def __init__(self, name):
        super(WebsiteView, self).__init__()
        self.name_btn.text = name

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


class SyncDirThread(threading.Thread):

    def __init__(self, site_name, path, client, callback):
        super(SyncDirThread, self).__init__()
        self.site_name = site_name
        self.path = path
        self.client = client
        self.callback = callback

    def run(self):
        app = App.get_running_app()
        domain = app.sites_dir_database[self.site_name]['domain'].encode('utf-8')
        try:
            status, msg_or_observer = self.client.sync(sitename=domain, path=self.path, interactive=False)
        except OSError as e:
            Clock.schedule_once(lambda dt: app.show_info_dialog('Filesystem Error', str(e)), 0)
        else:
            Clock.schedule_once(lambda dt: self.callback(self.site_name, status, msg_or_observer), 0)


class HTTPStaticServerThread(threading.Thread):

    def __init__(self, directory_mapping):
        super(HTTPStaticServerThread, self).__init__()
        self.directory_mapping = directory_mapping

    def run(self):
        self.httpd = get_static_server(STATIC_SERVER_PORT, self.directory_mapping)
        self.httpd.serve_forever()

    def shutdown(self):
        self.httpd.shutdown()


###########
# Helpers #
###########

class WebsitesManager(object):

    def __init__(self, sites_dir_database, sites_list_view):
        self._sites_dir_database = sites_dir_database
        self._sites_list_view = sites_list_view
        self._site_views_cache = {}
        self._site_sync_threads = {}

    def add_website(self, name, site_data):
        site_view = None
        if name in self._site_views_cache:
            site_view = self._site_views_cache[name]
        else:
            site_view = WebsiteView(name)

        site_dir = None
        if name in self._sites_dir_database:
            site_dir = self.get_site_dir(name)
        else:
            self._sites_dir_database[name] = {}
        self._sites_dir_database[name].update(site_data)

        site_view.set_site_dir_widgets(site_dir)

        if name in self._site_sync_threads:
            site_view.set_sync_btn_text_to_stop()
        else:
            site_view.set_sync_btn_text_to_sync()

        if name not in self._site_views_cache:
            self._sites_list_view.add_widget(site_view)
            self._site_views_cache[name] = site_view

    def remove_website(self, name):
        site_view = self._site_views_cache[name]
        self._sites_list_view.remove_widget(site_view)
        del self._site_views_cache[name]

        if name in self._site_sync_threads:
            site_sync_thread = self._site_sync_threads[name]
            site_sync_thread.stop()
            del self._site_sync_threads[name]

    def clear_websites(self):
        self._sites_list_view.clear_widgets()
        self._site_views_cache.clear()

        self.stop_all_threads()

    def stop_all_threads(self):
        for t in self._site_sync_threads.values():
            t.stop()
            t.join()
        self._site_sync_threads.clear()

    def get_sites_names(self):
        return self._site_views_cache.keys()

    def get_site_dashboard_url(self, name):
        return self._sites_dir_database[name].get('dashboard_url', CONTROL_PANEL_URL)

    ### Site's sync observer ###

    def _delete_site_sync_observer(self, site_name):
        observer = self.get_site_sync_observer(site_name)
        if observer:
            observer.stop()
            observer.join()
            del self._site_sync_threads[site_name]
            site_view = self._site_views_cache[site_name]
            site_view.set_sync_btn_text_to_sync()

    def set_site_sync_observer(self, site_name, observer):
        # stopping and removing any older syncing observer
        self._delete_site_sync_observer(site_name)

        self._site_sync_threads[site_name] = observer
        site_view = self._site_views_cache[site_name]
        site_view.set_sync_btn_text_to_stop()

    def get_site_sync_observer(self, site_name):
        return self._site_sync_threads.get(site_name, None)

    def stop_site_sync_observer(self, site_name):
        self._delete_site_sync_observer(site_name)

    ### Site's sync directory ###

    def get_site_dir(self, site_name):
        return self._sites_dir_database[site_name].get('dir', None)

    def set_site_dir(self, site_name, site_dir):
        self._sites_dir_database[site_name]['dir'] = site_dir
        self._sites_dir_database.sync()
        site_view = self._site_views_cache[site_name]
        site_view.set_site_dir_widgets(site_dir)


#############
# App class #
#############

class CMSCloudGUIApp(App):

    title = WINDOW_TITLE
    icon = "resources/appIcon.icns"

    def __init__(self, *args, **kwargs):
        super(CMSCloudGUIApp, self).__init__(*args, **kwargs)
        self.client = Client(os.environ.get(Client.CMSCLOUD_HOST_KEY, Client.CMSCLOUD_HOST_DEFAULT))
        sites_dir_database_file_path = os.path.join(self.user_data_dir, SITES_DATABASE_FILENAME)
        self.sites_dir_database = shelve.open(sites_dir_database_file_path, writeback=True)

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

    def on_start(self):
        super(CMSCloudGUIApp, self).on_start()

        sites_list_view = self._get_sites_list_view()
        self._websites_manager = WebsitesManager(self.sites_dir_database, sites_list_view)
        self.httpd_thread = HTTPStaticServerThread(self.sites_dir_database)
        self.httpd_thread.start()

        if self.client.is_logged_in():
            self.set_screen_to_sync()
        else:
            self.set_screen_to_login()

    def on_stop(self):
        self.sites_dir_database.close()
        self.config.write()
        self._websites_manager.stop_all_threads()
        self.httpd_thread.shutdown()
        super(CMSCloudGUIApp, self).on_stop()

    def set_screen_to_sync(self):
        Window.size = WIDTH_SYNC, HEIGHT_SYNC
        self.root.current = 'sync'
        self.load_sites_list()

    def set_screen_to_login(self):
        Window.size = WIDTH_LOGIN, HEIGHT_LOGIN
        self.root.current = 'login'

    ### DIALOGS ###

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

    def dismiss_confirm_dialog(self):
        if hasattr(self, '_confirm_popup') and self._confirm_popup:
            self._confirm_popup.dismiss()
            del self._confirm_popup

    def show_confirm_dialog(self, title, msg, on_confirm, on_open=None):

        def on_confirm_wrapper():
            self.dismiss_confirm_dialog()
            on_confirm()
        content = ConfirmDialog(confirm=on_confirm_wrapper, cancel=self.dismiss_confirm_dialog)
        content.message_label.text = msg
        self._confirm_popup = Popup(title="Confirm", auto_dismiss=False, content=content, size_hint=(0.9, None), height=200)
        if on_open:
            self._confirm_popup.on_open = on_open
        self._confirm_popup.open()

    def dismiss_loading_dialog(self):
        if hasattr(self, '_loading_popup') and self._loading_popup:
            self._loading_popup.dismiss()
            del self._loading_popup

    def show_loading_dialog(self, on_open=None):
        content = LoadingDialog()
        self._loading_popup = Popup(title='', auto_dismiss=False, content=content, size_hint=(0.9, None), height=200)
        if on_open:
            self._loading_popup.on_open = on_open
        self._loading_popup.open()

    def dismiss_dir_chooser_dialog(self):
        if hasattr(self, '_dir_chooser_popup') and self._dir_chooser_popup:
            self._dir_chooser_popup.dismiss()
            del self._dir_chooser_popup

    def show_dir_chooser_dialog(self, on_selection, path=None, on_open=None):

        def on_selection_wrapper(path, selection):
            self.dismiss_dir_chooser_dialog()
            on_selection(path, selection)
        content = DirChooserDialog(select=on_selection_wrapper, cancel=self.dismiss_dir_chooser_dialog)
        file_chooser = content.file_chooser
        file_chooser.path = path or self._get_last_dir()
        file_chooser.bind(path=lambda instance, path: self._set_last_dir(path))
        self._dir_chooser_popup = Popup(title="Choose directory", content=content, size_hint=(0.9, 0.9))
        if on_open:
            self._dir_chooser_popup.on_open = on_open
        self._dir_chooser_popup.open()

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
        self.show_loading_dialog()
        self._load_sites_list_thread = LoadSitesListThread(self.client, self._load_sites_list_callback)
        self._load_sites_list_thread.start()

    def _load_sites_list_callback(self, status, data):
        self.dismiss_loading_dialog()
        if status:
            new_sites_names = set()
            old_sites_names = set(self._websites_manager.get_sites_names())
            for site_data in data:
                name = site_data['name'].encode('utf-8')
                new_sites_names.add(name)
                self._websites_manager.add_website(name, site_data)

            removed_sites_names = old_sites_names - new_sites_names
            for removed_site_name in removed_sites_names:
                self._websites_manager.remove_website(removed_site_name)
        else:
            msg = unicode(data)
            self.show_info_dialog('Error', msg)

    def select_site_dir(self, site_name):
        on_selection = partial(self._select_site_dir_callback, site_name)
        site_dir = self._websites_manager.get_site_dir(site_name)
        self.show_dir_chooser_dialog(on_selection, path=site_dir)

    def _select_site_dir_callback(self, site_name, path, selection):
        if selection:
            site_dir = selection[0]
        else:
            site_dir = path
        self._websites_manager.set_site_dir(site_name, site_dir)

    def sync(self, site_name):
        observer = self._websites_manager.get_site_sync_observer(site_name)
        if observer:
            self._websites_manager.stop_site_sync_observer(site_name)
        else:
            site_dir = self._websites_manager.get_site_dir(site_name)
            if site_dir:
                on_confirm = partial(self._sync_confirmed, site_name, site_dir)
                title = 'Confirm sync'
                msg = 'All local changes to the boilerplate of "%s" will be undone. Continue?' % site_name
                self.show_confirm_dialog(title, msg, on_confirm)
            else:
                self.select_site_dir(site_name)

    def _sync_confirmed(self, site_name, site_dir):
        self.show_loading_dialog()
        path = site_dir.encode('utf-8')  # otherwise watchdog's observer crashed
        sync_dir_thread = SyncDirThread(site_name, path, self.client, self._sync_callback)
        sync_dir_thread.start()

    def _sync_callback(self, site_name, status, msg_or_observer):
        self.dismiss_loading_dialog()
        if status:  # observer
            self._websites_manager.set_site_sync_observer(site_name, msg_or_observer)
        else:  # msg
            self.show_info_dialog('Error', msg_or_observer)

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

    def browser_open_site_dashboard(self, site_name):
        webbrowser.open(self._websites_manager.get_site_dashboard_url(site_name))


if __name__ == '__main__':
    CMSCloudGUIApp().run()
