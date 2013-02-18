# -*- coding: utf-8 -*-
import ast

LLPY16_FUNCS = ['set']

def set(assembler, node, compiler):
    if len(node.args) != 2:
        return compiler.error("builtin_halt must be called with exactly two arguments", node)
    location = node.args[0]
    value = node.args[1]
    if isinstance(location, ast.BinOp):
        left = location.left
        op = location.op
        right = location.right
        if not isinstance(op, ast.Add):
            return compiler.error("Only + operator is allowed in memset arg one binp", op)
        try:
            left_value = assembler.resolve_nameish(left)
        except (TypeError, NameError):
            return compiler.error("Invalid left value in memset arg one binop %r" % left, left)
        try:
            right_value = assembler.resolve_nameish(right)
        except (TypeError, NameError):
            return compiler.error("Invalid right value in memset arg one binop %r" % right, right)
        location_value = "%s+%s" % (left_value, right_value)
    else:
        try:
            location_value = assembler.resolve_nameish(location)
        except (TypeError, NameError):
            return compiler.error("Invalid location value in memset %r" % location, location)

    assembler.write_instruction('SET', '[%s]' % location_value, assembler.resolve_nameish(value))
