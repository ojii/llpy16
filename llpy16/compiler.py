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


def register_or_number(node, assembler):
    if isinstance(node, ast.Name):
        value = node.id
        if value not in assembler.registers:
            raise CompilerError("Invalid register %r" % value, node)
        return value
    elif isinstance(node, ast.Num):
        return node.n
    else:
        raise CompilerError("Invalid type %r, expected number or register" % node, node)



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
        def resolve(thing):
            if isinstance(thing, ast.Num):
                return thing.n
            elif isinstance(thing, ast.Name):
                return thing.id
            else:
                raise TypeError(thing)
        function = self.context.resolve_function(node, self.assembler)
        if function:
            # handle args
            for arg, into in zip(node.args, function.args):
                self.assembler.SET(into, resolve(arg))
            # call function/subroutine
            self.assembler.JSR(function.name)
            # handle deferred
            if function.deferred:
                self._write_function(function.name, function.node)
                function.deferred = False

    def handle_FunctionDef(self, node):
        args = [arg.id for arg in node.args.args]
        name = self.context.define_function(node.name, args, node)

    def _write_function(self, name, node):
        with self.assembler.label(name):
            for child in node.body:
                self.handle(child)
            self.assembler.return_from_subroutine()

    def handle_Assign(self, node):
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            raise CompilerError("Invalid target %r" % target, target)
        register = target.id
        if register not in self.assembler.registers:
            raise CompilerError("Invalid register %r" % register, target)
        value = register_or_number(node.value, self.assembler)
        self.assembler.SET(register, value)



def do_compile(source, paths=None):
    if not paths:
        paths = []

    assembler = Assembler()
    context = Context([STDLIB_PATH] + paths)

    compiler = Compiler(assembler, context)

    compiler.compile(source)
    sys.stdout.write(assembler.get_assembled() + '\n')
