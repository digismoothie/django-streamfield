import collections

from django import forms
from django.core.exceptions import ValidationError
from django.forms.utils import ErrorList
from django.template.loader import render_to_string
from django.utils.functional import cached_property
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

# from wagtail.admin.staticfiles import versioned_static
from ..utils import versioned_static
from .base import Block, DeclarativeSubBlocksMetaclass
from .utils import js_dict

__all__ = ["BaseStructBlock", "StructBlock", "StructValue"]


class StructValue(collections.OrderedDict):
    """A class that generates a StructBlock value from provided sub-blocks
    name->value
    """

    def __init__(self, block, *args):
        super().__init__(*args)
        self.block = block
        self._generate_display_methods()

    def __html__(self):
        return self.block.render(self)

    def render_as_block(self, context=None):
        return self.block.render(self, context=context)

    @cached_property
    def bound_blocks(self):
        return collections.OrderedDict(
            [(name, block.bind(self.get(name))) for name, block in self.block.child_blocks.items()],
        )

    def _generate_display_methods(self):
        for name, block in self.block.child_blocks.items():
            method_name = f"get_{name}_display"
            if not hasattr(self, method_name):
                setattr(self, method_name, self._create_display_method(name, block))

    def _create_display_method(self, name, block):
        from streamfield.blocks.field_block import ChoiceBlock

        def display_method():
            value = self.get(name)
            if isinstance(block, ChoiceBlock):
                choices_dict = dict(block.field.choices)
                return choices_dict.get(value, str(value))
            return str(value)

        return display_method


class BaseStructBlock(Block):
    """
    local_blocks

    """

    def __init__(self, local_blocks=None, **kwargs):
        self._constructor_kwargs = kwargs

        super().__init__(**kwargs)

        # create a local (shallow) copy of base_blocks so that it can be
        # supplemented by local_blocks
        self.child_blocks = self.base_blocks.copy()

        if local_blocks:
            for _name, block in local_blocks:
                # assert local blocks are instances
                if not (isinstance(block, Block)):
                    block = block()
                block.set_name(_name)
                self.child_blocks[_name] = block

        self.child_js_initializers = {}
        for name, block in self.child_blocks.items():
            js_initializer = block.js_initializer()
            if js_initializer is not None:
                self.child_js_initializers[name] = js_initializer

        self.dependencies = self.child_blocks.values()

    def get_default(self):
        """
        Any default value passed in the constructor or self.meta is going to be a dict
        rather than a StructValue; for consistency, we need to convert it to a StructValue
        for StructBlock to work with
        """
        return self._to_struct_value(self.meta.default.items())

    def js_initializer(self):
        # skip JS setup entirely if no children have js_initializers
        if not self.child_js_initializers:
            return None

        return "StructBlock(%s)" % js_dict(self.child_js_initializers)

    @property
    def media(self):
        return forms.Media(js=[versioned_static("streamfield/js/blocks/struct.js")])

    def get_form_context(self, value, prefix="", errors=None):
        if errors:
            if len(errors) > 1:
                # We rely on StructBlock.clean throwing a single ValidationError with a specially crafted
                # 'params' attribute that we can pull apart and distribute to the child blocks
                raise TypeError("StructBlock.render_form unexpectedly received multiple errors")
            error_dict = errors.as_data()[0].params
        else:
            error_dict = {}

        bound_child_blocks = collections.OrderedDict(
            [
                (
                    name,
                    block.bind(
                        value.get(name, block.get_default()),
                        prefix=f"{prefix}-{name}",
                        errors=error_dict.get(name),
                    ),
                )
                for name, block in self.child_blocks.items()
            ],
        )

        return {
            "children": bound_child_blocks,
            "help_text": getattr(self.meta, "help_text", None),
            "block_definition": self,
            "prefix": prefix,
        }

    def render_form(self, value, prefix="", errors=None):
        context = self.get_form_context(value, prefix=prefix, errors=errors)

        return mark_safe(render_to_string(self.meta.form_template, context))

    def value_from_datadict(self, data, files, prefix):
        return self._to_struct_value(
            [
                (name, block.value_from_datadict(data, files, f"{prefix}-{name}"))
                for name, block in self.child_blocks.items()
            ],
        )

    def value_omitted_from_data(self, data, files, prefix):
        return all(
            block.value_omitted_from_data(data, files, f"{prefix}-{name}") for name, block in self.child_blocks.items()
        )

    def clean(self, value):
        result = []  # build up a list of (name, value) tuples to be passed to the StructValue constructor
        errors = {}
        for name, val in value.items():
            try:
                result.append((name, self.child_blocks[name].clean(val)))
            except ValidationError as e:
                errors[name] = ErrorList([e])

        if errors:
            # The message here is arbitrary - StructBlock.render_form will suppress it
            # and delegate the errors contained in the 'params' dict to the child blocks instead
            raise ValidationError("Validation error in StructBlock", params=errors)

        return self._to_struct_value(result)

    def to_python(self, value):
        """Recursively call to_python on children and return as a StructValue"""
        return self._to_struct_value(
            [
                (
                    name,
                    (child_block.to_python(value[name]) if name in value else child_block.get_default()),
                    # NB the result of get_default is NOT passed through to_python, as it's expected
                    # to be in the block's native type already
                )
                for name, child_block in self.child_blocks.items()
            ],
        )

    def _to_struct_value(self, block_items):
        """Return a Structvalue representation of the sub-blocks in this block"""
        return self.meta.value_class(self, block_items)

    def get_prep_value(self, value):
        """Recursively call get_prep_value on children and return as a plain dict"""
        return {name: self.child_blocks[name].get_prep_value(val) for name, val in value.items()}

    # def pre_save_hook(self, field_value, value):
    # # child is a StreamChild instance
    # for name, value in value.items():
    # self.child_blocks[name].pre_save_hook(field_value, value)

    def get_searchable_content(self, value):
        content = []

        for name, block in self.child_blocks.items():
            content.extend(block.get_searchable_content(value.get(name, block.get_default())))

        return content

    def deconstruct(self):
        """
        Always deconstruct StructBlock instances as if they were plain StructBlocks with all of the
        field definitions passed to the constructor - even if in reality this is a subclass of StructBlock
        with the fields defined declaratively, or some combination of the two.

        This ensures that the field definitions get frozen into migrations, rather than leaving a reference
        to a custom subclass in the user's models.py that may or may not stick around.
        """
        path = "streamfield.blocks.StructBlock"
        args = [list(self.child_blocks.items())]
        kwargs = self._constructor_kwargs
        return (path, args, kwargs)

    def check(self, **kwargs):
        errors = super().check(**kwargs)
        for name, child_block in self.child_blocks.items():
            errors.extend(child_block.check(**kwargs))
            errors.extend(child_block._check_name(**kwargs))

        return errors

    def render_basic(self, value, context=None):
        struct = format_html_join(
            "\n",
            "{0}",
            # [
            # (child.render(context=context),)
            # for child in value.values()
            # ]
            [(block.render(value[name], context),) for name, block in self.child_blocks.items()],
        )
        return format_html(
            "<div{1}>{0}</div>",
            struct,
            self.render_css_classes(context),
        )

    class Meta:
        default = {}
        form_template = "streamfield/block_forms/struct.html"
        value_class = StructValue


class StructBlock(BaseStructBlock, metaclass=DeclarativeSubBlocksMetaclass):
    """
    A fixed collection of not similar blocks.
    Compare to ListBlock, a collection of similar blocks,
    and StreamField, a not-fixed collection of not similar blocks.
    """

    pass
