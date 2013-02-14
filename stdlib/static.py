# -*- coding: utf-8 -*-
import ast

LLPY16_FUNCS = [
    'write',
    'char'
]

LLPY16_NAMES = [
    'color_black',
    'color_dark_blue',
    'color_green',
    'color_teal',
    'color_purple',
    'color_dark_red',
    'color_brown',
    'color_light_gray',
    'color_gray',
    'color_blue',
    'color_light_green',
    'color_light_blue',
    'color_red',
    'color_pink',
    'color_yellow',
    'color_white',
]

color_black = 0
color_dark_blue = 1
color_green = 2
color_teal = 3
color_purple = 4
color_dark_red = 5
color_brown = 6
color_light_gray = 7
color_gray = 8
color_blue = 9
color_light_green = 10
color_light_blue = 11
color_red = 12
color_pink = 13
color_yellow = 14
color_white = 15


char_code_map = dict((i, chr(i)) for i in range(126))

char_lookup_map = dict((value, key) for key, value in char_code_map.items())


def _resolve_color(color):
    if isinstance(color, ast.Num):
        return color.n
    else:
        return globals()['color_%s' % color.id]

def write(assembler, node, compiler):
    """
    static.write(text, position, color, highlight_color)
    """
    if len(node.args) != 4:
        return compiler.error("static.write must be called with 4 arguments, not %s" % len(node.args))
    text, position, color, highlight_color = node.args
    if not isinstance(text, ast.Str):
        return compiler.error("first argument to static.write must be a string", text)
    if not isinstance(position, ast.Num):
        return compiler.error("second argument to static.write must be an integer", position)
    if not isinstance(color, (ast.Num, ast.Name)):
        return compiler.error("third argument to static.write must be a number or a constant", color)
    if not isinstance(highlight_color, (ast.Num, ast.Name)):
        return compiler.error("fourth argument to static.write must be a number or a constant", color)
    text_value = text.s
    position_value = position.n
    color_value = _resolve_color(color)
    highlight_color_value = _resolve_color(highlight_color)
    for offset, char in enumerate(text_value):
        location = 0x8000 + position_value + offset
        value = (color_value << 12) | (highlight_color_value << 8) | ord(char)
        assembler.write_instruction('SET', '[%s]' % location, value)

def char(assembler, node, compiler):
    pass
