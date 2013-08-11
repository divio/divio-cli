# -*- coding: utf-8 -*-
import os


VALID_FIELD_TYPES = [
    'text',
    'checkbox',
    'number',
    'select',
    'x-static-file',
]


class ValidationError(Exception):
    def __init__(self, message):
        self.message = message


class BaseField(object):
    field_type = None

    def __init__(self, label, required=True):
        self.label = label
        self.required = required

    def clean(self, value):
        return value

    def serialize(self):
        return {
            'field_type': self.field_type,
            'label': self.label,
            'required': self.required
        }


class CharField(BaseField):
    field_type = 'text'

    def __init__(self, label, min_length=None, max_length=None, required=True):
        super(CharField, self).__init__(label, required)
        self.min_length = min_length
        self.max_length = max_length

    def clean(self, value):
        if not value:
            value = ''
        length = len(value)
        if self.min_length and length < self.min_length:
            raise ValidationError("Value must be at least %s characters, got %s characters" % (self.min_length, length))
        if self.max_length and length > self.max_length:
            raise ValidationError("Value must be less than %s characters, got %s characters" % (self.max_length, length))
        return value

    def serialize(self):
        data = super(CharField, self).serialize()
        data['min_length'] = self.min_length
        data['max_length'] = self.max_length
        return data


class CheckboxField(BaseField):
    field_type = 'checkbox'

    def clean(self, value):
        return bool(value)


class SelectField(BaseField):
    field_type = 'select'

    def __init__(self, label, choices, required=True):
        super(SelectField, self).__init__(label, required)
        self.choices = choices

    def serialize(self):
        data = super(SelectField, self).serialize()
        data['choices'] = self.choices
        return data


class NumberField(BaseField):
    field_type = 'number'

    def __init__(self, label, min_value=None, max_value=None, required=True):
        super(NumberField, self).__init__(label, required)
        self.min_value = min_value
        self.max_value = max_value

    def clean(self, value):
        if not value:
            return value
        if not value.isdigit():
            raise ValidationError("Expected number, but got %s" % value)
        value = int(value)
        if self.min_value is not None and value < self.min_value:
            raise ValidationError("Must be bigger than %s"  % self.min_value)
        if self.max_value is not None and value > self.max_value:
            raise ValidationError("Must be smaller than %s" % self.max_value)
        return value


class StaticFileField(BaseField):
    field_type = 'x-static-file'

    def __init__(self, label, extensions=None, required=True):
        super(StaticFileField, self).__init__(label, required)
        self.extensions = extensions

    def clean(self, value):
        if not value:
            return value
        extension = os.path.splitext(value)[1][1:]
        if self.extensions is not None and extension not in self.extensions:
            raise ValidationError("Please choose a file with one of the following extensions: %s." % ', '.join(self.extensions))
        return value

    def serialize(self):
        data = super(StaticFileField, self).serialize()
        data['extensions'] = self.extensions
        return data


class FormMeta(type):
    def __new__(cls, name, bases, attrs):
        fields = []
        for key, value in attrs.items():
            if isinstance(value, BaseField):
                fields.append((key, value))
        attrs['_fields'] = fields
        return super(FormMeta, cls).__new__(cls, name, bases, attrs)


class BaseForm(object):
    __metaclass__ = FormMeta

    def __init__(self, data=None):
        self.data = data or {}

    def serialize(self):
        form = []
        for name, field in self._fields:
            form.append((name, field.serialize()))
        return form

    def is_valid(self):
        self.cleaned_data = {}
        self.errors = {}
        try:
            self.clean()
        except ValidationError, e:
            self.errors[None] = e.message
        return not self.errors

    def clean(self):
        for name, field in self._fields:
            value = self.data.get(name, None)
            if field.required and value is None:
                self.errors[name] = "This field is required"
            else:
                try:
                    self.cleaned_data[name] = field.clean(value)
                except ValidationError, e:
                    self.errors[name] = e.message

    def to_settings(self, data, settings):
        return settings

    def save(self):
        return self.cleaned_data
