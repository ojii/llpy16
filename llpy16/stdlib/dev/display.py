# -*- coding: utf-8 -*-

LLPY16_EXTS = [
    'write_static',
]

def write_static(assembler, context, text, location, color, highlight_color):
    for offset, char in enumerate(text):
        assembler.SET('[%s]' % (location + offset), ord(char) | (color << 12) | (highlight_color << 8))
