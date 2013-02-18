# -*- coding: utf-8 -*-

LLPY16_EXTS = [
    'configure',
    'write_static',
]

def configure(assembler, context, **kwargs):
    for key, value in kwargs.items():
        context.set_config(key, value)

def write_static(assembler, context, text, location, color=None, highlight_color=None):
    color = (color or context.get_config('color')) << 12
    highlight_color = (highlight_color or context.get_config('highlight_color')) << 8
    for offset, char in enumerate(text):
        assembler.SET('[%s]' % (location + offset), ord(char) | color | highlight_color)
