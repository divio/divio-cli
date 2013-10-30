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
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.screenmanager import Screen, ScreenManager, TransitionBase
from kivy.utils import get_color_from_hex

from client import Client
from utils_kivy import TabTextInput, open_in_file_manager, notify

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

# status to dot color mapping
STATUS_TO_COLOR = {
    0: get_color_from_hex('#4a9cf2'),  # NEW, blue
    1: get_color_from_hex('#98ba0f'),  # DEPLOYED, green
    2: get_color_from_hex('#4a9cf2'),  # DEPLOYING, blue
    3: get_color_from_hex('#626262'),  # OFFLINE, grey
    4: get_color_from_hex('#f0453b'),  # ERROR, red
}


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
    cancel_callback = ObjectProperty(None)
    confirm_callback = ObjectProperty(None)
    message_label = ObjectProperty(None)
    cancel_btn_text = ObjectProperty(None)
    confirm_btn_text = ObjectProperty(None)


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


class CustomFileChooserListView(FileChooserListView):

    def go_to_home_dir(self):
        self.path = HOME_DIR


class WebsiteView(RelativeLayout):
    status_btn = ObjectProperty(None)
    name_btn = ObjectProperty(None)
    dir_label = ObjectProperty(None)
    change_or_set_dir_btn = ObjectProperty(None)
    open_dir_btn = ObjectProperty(None)
    sync_btn = ObjectProperty(None)
    preview_btn = ObjectProperty(None)

    domain = StringProperty(None)

    def __init__(self, domain):
        super(WebsiteView, self).__init__()
        self.domain = domain

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
        Clock.schedule_once(lambda dt: self.callback(status, data), 0)


class SyncDirThread(threading.Thread):

    def __init__(self, domain, path, client, sync_callback, stop_sync_callback):
        super(SyncDirThread, self).__init__()
        self.domain = domain
        self.path = path
        self.client = client
        self.sync_callback = sync_callback
        self.stop_sync_callback = stop_sync_callback

    def run(self):
        app = App.get_running_app()
        domain = app.sites_dir_database[self.domain]['domain'].encode('utf-8')
        try:
            status, msg_or_observer = self.client.sync(
                sitename=domain, path=self.path,
                stop_sync_callback=self.stop_sync_callback)
        except OSError as e:
            Clock.schedule_once(
                lambda dt: app.show_info_dialog('Filesystem Error', str(e)), 0)
        else:
            Clock.schedule_once(
                lambda dt: self.sync_callback(
                    self.domain, status, msg_or_observer), 0)


###########
# Helpers #
###########

class WebsitesManager(object):

    def __init__(self, sites_dir_database, sites_list_view):
        self._sites_dir_database = sites_dir_database
        self._sites_list_view = sites_list_view
        self._site_views_cache = {}
        self._site_sync_threads = {}

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

        if domain in self._site_sync_threads:
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

        if domain in self._site_sync_threads:
            site_sync_thread = self._site_sync_threads[domain]
            site_sync_thread.stop()
            del self._site_sync_threads[domain]

    def clear_websites(self):
        self._sites_list_view.clear_widgets()
        self._site_views_cache.clear()

        self.stop_all_threads()

    def stop_all_threads(self):
        for t in self._site_sync_threads.values():
            t.stop()
            t.join()
        self._site_sync_threads.clear()

    def get_site_name(self, domain):
        return self._sites_dir_database[domain]['name'].encode('utf-8')

    def get_domain(self):
        return self._site_views_cache.keys()

    def get_site_dashboard_url(self, domain):
        return self._sites_dir_database[domain].get(
            'dashboard_url', CONTROL_PANEL_URL)

    def get_site_stage_url(self, domain):
        return self._sites_dir_database[domain].get(
            'stage_url', CONTROL_PANEL_URL)

    ### Site's sync observer ###

    def _delete_site_sync_observer(self, domain):
        observer = self.get_site_sync_observer(domain)
        if observer:
            observer.stop()
            observer.join()
            del self._site_sync_threads[domain]
            site_view = self._site_views_cache[domain]
            site_view.set_sync_btn_text_to_sync()

    def set_site_sync_observer(self, domain, observer):
        # stopping and removing any older syncing observer
        self._delete_site_sync_observer(domain)

        self._site_sync_threads[domain] = observer
        site_view = self._site_views_cache[domain]
        site_view.set_sync_btn_text_to_stop()

    def get_site_sync_observer(self, domain):
        return self._site_sync_threads.get(domain, None)

    def stop_site_sync_observer(self, domain):
        self._delete_site_sync_observer(domain)

    ### Site's sync directory ###

    def get_site_dir(self, domain):
        return self._sites_dir_database[domain].get('dir', None)

    def set_site_dir(self, domain, site_dir):
        self._sites_dir_database[domain]['dir'] = site_dir
        self._sites_dir_database.sync()
        site_view = self._site_views_cache[domain]
        site_view.set_site_dir_widgets(site_dir)


#############
# App class #
#############

class CMSCloudGUIApp(App):

    title = WINDOW_TITLE
    icon = "resources/appIcon.icns"

    def __init__(self, *args, **kwargs):
        super(CMSCloudGUIApp, self).__init__(*args, **kwargs)
        self.client = Client(
            os.environ.get(Client.CMSCLOUD_HOST_KEY, Client.CMSCLOUD_HOST_DEFAULT),
            interactive=False)
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

        if self.client.is_logged_in():
            self.set_screen_to_sync()
        else:
            self.set_screen_to_login()

    def on_stop(self):
        self.sites_dir_database.close()
        self.config.write()
        self._websites_manager.stop_all_threads()
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

    def show_confirm_dialog(self, title, msg, on_confirm,
                            cancel_btn_text='Cancel',
                            confirm_btn_text='Confirm',
                            on_open=None):

        def on_confirm_wrapper():
            self.dismiss_confirm_dialog()
            on_confirm()

        content = ConfirmDialog(confirm_callback=on_confirm_wrapper,
                                cancel_callback=self.dismiss_confirm_dialog,
                                cancel_btn_text=cancel_btn_text,
                                confirm_btn_text=confirm_btn_text)
        content.message_label.text = msg
        self._confirm_popup = Popup(
            title=title, content=content,
            auto_dismiss=False, size_hint=(0.9, None), height=200)
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
            self.dismiss_dir_chooser_dialog()
            on_selection(dir_path)

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
        self.show_loading_dialog()
        self._load_sites_list_thread = LoadSitesListThread(self.client, self._load_sites_list_callback)
        self._load_sites_list_thread.start()

    def _load_sites_list_callback(self, status, data):
        self.dismiss_loading_dialog()
        if status:
            new_sites_names = set()
            old_sites_names = set(self._websites_manager.get_domain())
            for site_data in data:
                domain = site_data['domain'].encode('utf-8')
                new_sites_names.add(domain)
                self._websites_manager.add_or_update_website(
                    domain, site_data)
            removed_sites_names = old_sites_names - new_sites_names
            for removed_domain in removed_sites_names:
                self._websites_manager.remove_website(removed_domain)
        else:
            msg = unicode(data)
            self.show_info_dialog('Error', msg)

    def select_site_dir(self, domain):
        on_selection = partial(self._select_site_dir_callback, domain)
        site_dir = self._websites_manager.get_site_dir(domain)
        self.show_dir_chooser_dialog(on_selection, path=site_dir)

    def _select_site_dir_callback(self, domain, site_dir):
        self._websites_manager.set_site_dir(domain, site_dir)

    ### SYNC ###

    def sync_toggle(self, domain):
        observer = self._websites_manager.get_site_sync_observer(domain)
        if observer:
            self.stop_sync(domain)
        else:
            site_dir = self._websites_manager.get_site_dir(domain)
            if site_dir:
                on_confirm = partial(self._sync_confirmed, domain, site_dir)
                title = 'Confirm sync'
                name = self._websites_manager.get_site_name(domain)
                msg = 'All local changes to the boilerplate of "%s" will be undone. Continue?' % name
                self.show_confirm_dialog(title, msg, on_confirm)
            else:
                self.select_site_dir(domain)

    def stop_sync(self, domain):
        self._websites_manager.stop_site_sync_observer(domain)

    def _sync_confirmed(self, domain, site_dir):
        self.show_loading_dialog()
        path = site_dir.encode('utf-8')  # otherwise watchdog's observer crashed
        stop_sync_callback = partial(self._stop_sync_callback, domain)
        sync_dir_thread = SyncDirThread(
            domain, path, self.client, self._sync_callback, stop_sync_callback)
        sync_dir_thread.start()

    def _sync_callback(self, domain, status, msg_or_observer):
        self.dismiss_loading_dialog()
        if status:  # observer
            self._websites_manager.set_site_sync_observer(domain, msg_or_observer)
        else:  # msg
            self.show_info_dialog('Error', msg_or_observer)

    def _stop_sync_callback(self, domain, msg):
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
        webbrowser.open(self._websites_manager.get_site_dashboard_url(domain))

    def browser_open_stage(self, domain):
        webbrowser.open(self._websites_manager.get_site_stage_url(domain))


if __name__ == '__main__':
    CMSCloudGUIApp().run()
