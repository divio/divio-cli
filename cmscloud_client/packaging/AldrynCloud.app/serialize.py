# -*- coding: utf-8 -*-
from collections import defaultdict
from distutils.version import StrictVersion
import hashlib
import shutil
import glob

import os
import yaml


# YAML STUFF
class Tracker(object):
    def __init__(self):
        self.contexts = []

    def push(self, thing):
        for context in self.contexts:
            context[thing.__class__].append(thing)

    def __enter__(self):
        context = defaultdict(list)
        self.contexts.append(context)
        return context

    def __exit__(self, exc_type, exc_val, exc_tb):
        del self.contexts[-1]


class Trackable(object):
    tracker = Tracker()

    def __init__(self):
        self.tracker.push(self)


class Include(Trackable):
    def __init__(self, path):
        super(Include, self).__init__()
        self.path = path


class ListInclude(Include): pass


class File(Include): pass


class LiteralInclude(Include): pass


class Model(Trackable):
    def __init__(self, app_label, model_name):
        super(Model, self).__init__()
        self.app_label = app_label
        self.model_name = model_name

    def load(self):
        from django.db.models.loading import get_model

        return get_model(self.app_label, self.model_name)


def include_constructor(loader, node):
    value = loader.construct_scalar(node).lstrip('/')
    with open(value) as fobj:
        return yaml.safe_load(fobj)


def include_representer(dumper, data):
    return dumper.represent_scalar(u'!include', u'%s' % data.path)


def list_include_constructor(loader, node):
    value = loader.construct_scalar(node).lstrip('/')
    data = []
    for fname in glob.glob(value):
        with open(fname) as fobj:
            data += yaml.safe_load(fobj)
    return data


def list_include_representer(dumper, data):
    return dumper.represent_scalar(u'!list-include', data.path)


def file_constructor(loader, node):
    path = loader.construct_scalar(node)
    return File(path)


def file_representer(dumper, data):
    return dumper.represent_scalar(u'!file', data.path)


def literal_include_constructor(loader, node):
    with open(loader.construct_scalar(node).lstrip('/')) as fobj:
        return fobj.read()


def literal_include_representer(dumper, data):
    return dumper.represent_scalar(u'!literal-include', data.path)


def model_representer(dumper, data):
    return dumper.represent_scalar(u'!model', '%s.%s' % (data.app_label, data.model_name))


def model_constructor(loader, node):
    name_string = loader.construct_scalar(node)
    app_label, model_name = name_string.split('.')
    return Model(app_label, model_name)


__registerered = False


def register_yaml_extensions():
    global __registerered
    if __registerered:
        return

    yaml.add_constructor(u'!include', include_constructor, yaml.SafeLoader)
    yaml.add_constructor(u'!include-list', list_include_constructor, yaml.SafeLoader)
    yaml.add_constructor(u'!literal-include', literal_include_constructor, yaml.SafeLoader)
    yaml.add_constructor(u'!file', file_constructor, yaml.SafeLoader)
    yaml.add_constructor(u'!model', model_constructor, yaml.SafeLoader)
    yaml.add_representer(Include, include_representer, yaml.SafeDumper)
    yaml.add_representer(ListInclude, list_include_representer, yaml.SafeDumper)
    yaml.add_representer(File, file_representer, yaml.SafeDumper)
    yaml.add_representer(LiteralInclude, literal_include_representer, yaml.SafeDumper)
    yaml.add_representer(Model, model_representer, yaml.SafeDumper)

    __registerered = True

# DUMP


class Dumper(object):
    def __init__(self, datadir, language, follow=None):
        from django.utils.translation import activate

        activate(language)
        register_yaml_extensions()
        self.datadir = datadir
        if os.path.exists(self.datadir):
            shutil.rmtree(self.datadir)
        os.mkdir(self.datadir)
        self.file_count = 0
        self.language = language
        self.follow = defaultdict(list)
        if follow:
            for key, value in (thing.split('.', 1) for thing in follow):
                self.follow[key].append(value)
        from cms import models

        self.queryset = models.Page.objects.root().public()
        self.file_cache = {}

    def dump(self, filename):
        data = self.get_pages()
        with open(filename, 'w') as fobj:
            yaml.safe_dump(data, fobj)

    def get_pages(self):
        data = []
        for page in self.queryset:
            data.append(self.serialize_page(page))
        return data

    def serialize_page(self, page):
        return {
            'path': page.get_absolute_url(),
            'name': page.get_title(),
            'template': page.template,
            'placeholders': [self.serialize_placeholder(page, ph) for ph in page.placeholders.all()],
            'children': [self.serialize_page(child) for child in page.get_children()],
        }

    def serialize_placeholder(self, page, placeholder):
        plugins = self.dump_plugins(page, placeholder)
        return {
            'name': placeholder.slot,
            'plugins': Include(plugins)
        }

    def dump_plugins(self, page, placeholder):
        filename = os.path.join(self.datadir, '%s_%s.yaml' % (placeholder.slot, page.pk))
        data = [self.serialize_plugin(plugin) for plugin in
                placeholder.cmsplugin_set.filter(language=self.language, parent__isnull=True).order_by('position')]
        with open(filename, 'w') as fobj:
            yaml.safe_dump(data, fobj)
        return filename

    def serialize_plugin(self, plugin):
        from django.forms.models import model_to_dict

        instance = plugin.get_plugin_instance()[0]
        raw_data = model_to_dict(instance)
        raw_data.pop('cmsplugin_ptr', None)
        del raw_data['id']
        raw_data['plugin_type'] = plugin.plugin_type
        raw_data['-relations'] = []
        raw_data['-children'] = []
        self.post_process_files(raw_data)
        self.post_process_relations(instance, plugin, raw_data)
        self.post_process_children(instance, plugin, raw_data)
        return raw_data

    def post_process_files(self, raw_data):
        from django.db.models.fields.files import FieldFile, ImageFieldFile

        for key, value in raw_data.items():
            if isinstance(value, (FieldFile, ImageFieldFile)):
                if value:
                    data = ''
                    for chunk in value.chunks():
                        data += chunk
                        #de-dup
                    checksum = hashlib.md5(data).hexdigest()
                    if checksum not in self.file_cache:
                        filename = os.path.join(self.datadir, '_file_%s' % self.file_count)
                        self.file_count += 1
                        with open(filename, 'wb') as target:
                            target.write(data)
                        self.file_cache[checksum] = filename
                    raw_data[key] = File(self.file_cache[checksum])
                else:
                    raw_data[key] = None

    def post_process_relations(self, instance, plugin, raw_data):
        for field in self.follow['%s:%s' % (instance._meta.app_label, instance._meta.module_name)]:
            objects = getattr(instance, field).all()
            raw_data['-relations'] += [self.serialize_plugin_relation(instance, obj) for obj in objects]

    def serialize_plugin_relation(self, plugin, obj):
        from django.forms.models import model_to_dict
        from django.db.models.fields.related import ForeignKey

        data = model_to_dict(obj, fields=obj._meta.get_all_field_names())
        for field_name in obj._meta.get_all_field_names():
            field = obj._meta.get_field_by_name(field_name)[0]
            if isinstance(field, ForeignKey):
                if getattr(obj, field_name) == plugin:
                    del data[field_name]
                    data['-field'] = field_name
            elif field_name not in data:
                data[field_name] = field.value_from_object(obj)
        del data['id']
        self.post_process_files(data)
        data['-model'] = Model(obj._meta.app_label, obj.__class__.__name__)
        return data

    def post_process_children(self, instance, plugin, raw_data):
        pass

# LOAD

class Loader(object):
    def __init__(self, language):
        from django.utils.translation import activate

        activate(language)
        register_yaml_extensions()

    def syncdb(self):
        from django.core.management import call_command
        from django.conf import settings

        call_command('syncdb', interactive=False)
        if 'south' in settings.INSTALLED_APPS:
            call_command('migrate', interactive=False)

    def load(self, filename):
        self.syncdb()
        from cms.models import Page, Placeholder
        self.placeholder_does_not_exist = Placeholder.DoesNotExist

        if Page.objects.exists():
            print "Non-empty database, aborting"
            return
        with open(filename) as fobj:
            data = yaml.safe_load(fobj)
            for page in data:
                self.load_page(page)

    def load_page(self, data, parent=None):
        from cms.api import create_page
        from cms.models import Page
        from django.utils.translation import get_language

        if parent:
            parent = Page.objects.get(pk=parent.pk)
        page = create_page(data['name'], data['template'], get_language(), parent=parent,
                           in_navigation=True, published=True)
        for placeholder in data['placeholders']:
            self.load_placeholder(placeholder, page)
        for child in data['children']:
            self.load_page(child, page)
        page.publish()

    def load_placeholder(self, data, page):
        try:
            placeholder = page.placeholders.get(slot=data['name'])
        except self.placeholder_does_not_exist:
            placeholder = page.placeholders.create(slot=data['name'])
        for plugin in data['plugins']:
            self.load_plugin(plugin, placeholder)

    def load_plugin(self, data, placeholder, parent=None):
        from cms.api import add_plugin
        from django.utils.translation import get_language

        plugin_type = data.pop('plugin_type')
        relations = data.pop('-relations')
        children = data.pop('-children')
        self.pre_process_files(data)
        plugin = add_plugin(placeholder, plugin_type, get_language(), target=parent, **data)
        for child in children:
            self.load_plugin(child, placeholder, plugin)
        for relation in relations:
            self.load_relation(relation, plugin)

    def pre_process_files(self, data):
        from django.core.files.base import File as DjangoFile

        for key, value in data.items():
            if isinstance(value, File):
                data[key] = DjangoFile(open(value.path))

    def load_relation(self, data, plugin):
        model = data.pop('-model').load()
        plugin_field = data.pop('-field')
        data[plugin_field] = plugin
        model.objects.create(**data)
