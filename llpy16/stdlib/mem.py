# -*- coding: utf-8 -*-
import ast

LLPY16_EXTS = [
    'set_string',
    'set',
]

def set_string(assembler, context, start, text, color, highlight_color):
    for offset, char in enumerate(text):
        assembler.SET('[%s]' % (start + offset), ord(char) | (color << 12) | (highlight_color << 8))

def set(assembler, context, location, value):
    assembler.SET('[%s]' % location, value)
