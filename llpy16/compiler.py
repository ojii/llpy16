# -*- coding: utf-8 -*-
import ast
import sys
from . import STDLIB_PATH
from .assembler import Assembler
from .context import Context


class CompilerError(Exception):
    def __init__(self, message, node):
        if hasattr(node, 'lineno') and hasattr(node, 'col_offset'):
            info = '%s(%s): ' % (node.lineno, node.col_offset)
        else:
            info = ''
        super(CompilerError, self).__init__('%s%s' % (info, message))


class UnsupportedNode(CompilerError):
    def __init__(self, node):
        super(UnsupportedNode, self).__init__("Unsupported node type %r" % node, node)


class Compiler(object):
    def __init__(self, assembler, context):
        self.assembler = assembler
        self.context = context

    def compile(self, source):
        node = ast.parse(source)
        self.handle(node)

    def handle(self, node):
        handler = getattr(self, 'handle_%s' % node.__class__.__name__, None)
        if handler is None:
            raise UnsupportedNode(node)
        else:
            handler(node)

    def handle_Module(self, node):
        for child in node.body:
            self.handle(child)

    def handle_Import(self, node):
        for alias in node.names:
            if alias.asname:
                raise UnsupportedNode(alias.asname)
            name = alias.name
            source = self.context.find_import(name, self.assembler)
            if source:
                with self.context.namespace(name):
                    self.compile(source)

    def handle_Expr(self, node):
        self.handle(node.value)

    def handle_Call(self, node):
        function_name = self.context.resolve_function(node, self.assembler)
        if function_name:
            self.assembler.JSR(function_name)


def do_compile(source, paths=None):
    if not paths:
        paths = []

    assembler = Assembler()
    context = Context([STDLIB_PATH] + paths)

    compiler = Compiler(assembler, context)

    compiler.compile(source)
    sys.stdout.write(assembler.get_assembled() + '\n')
