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

def get_register(node, assembler):
    if not isinstance(node, ast.Name):
        raise CompilerError("Invalid target %r" % node, node)
    register = node.id
    if register not in assembler.registers:
        raise CompilerError("Invalid register %r" % register, node)
    return register

def get_register_or_number(node, assembler):
    if isinstance(node, ast.Name):
        return get_register(node, assembler)
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
            elif isinstance(thing, ast.List):
                return '[%s]' % resolve(thing.elts[0])
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
                self.write_function(function)
                function.deferred = False

    def handle_FunctionDef(self, node):
        args = [arg.id for arg in node.args.args]
        function = self.context.define_function(node.name, args, node)
        if node.decorator_list:
            if len(node.decorator_list) > 1:
                raise CompilerError("Functions can only have one decorator", node)
            self.write_function(function)
            decorator = node.decorator_list[0]
            tree = ast.Call(
                func=decorator,
                args=[ast.List(elts=[ast.Name(id=node.name)])]
            )
            self.handle(tree)

    def write_function(self, function):
        with self.assembler.label(function.name):
            for child in function.node.body:
                self.handle(child)
            self.assembler.return_from_subroutine()

    def handle_Assign(self, node):
        register = get_register(node.targets[0], self.assembler)
        value = get_register_or_number(node.value, self.assembler)
        self.assembler.SET(register, value)

    def handle_AugAssign(self, node):
        if isinstance(node.op, ast.Add):
            instruction = self.assembler.ADD
        elif isinstance(node.op, ast.Sub):
            instruction = self.assembler.SUB
        elif isinstance(node.op, ast.Mult):
            instruction = self.assembler.MUL
        elif isinstance(node.op, ast.Div):
            instruction = self.assembler.DIV
        elif isinstance(node.op, ast.LShift):
            instruction = self.assembler.SHL
        elif isinstance(node.op, ast.RShift):
            instruction = self.assembler.SHR
        elif isinstance(node.op, ast.BitOr):
            instruction = self.assembler.BOR
        elif isinstance(node.op, ast.BitAnd):
            instruction = self.assembler.AND
        elif isinstance(node.op, ast.BitXor):
            instruction = self.assembler.XOR
        else:
            raise CompilerError("Invalid augmented assignment, operator %r not supported" % node.op, node.op)
        register = get_register(node.target, self.assembler)
        value = get_register_or_number(node.value, self.assembler)
        instruction(register, value)


def do_compile(source, paths=None):
    if not paths:
        paths = []

    assembler = Assembler()
    context = Context([STDLIB_PATH] + paths)

    compiler = Compiler(assembler, context)

    compiler.compile(source)
    sys.stdout.write(assembler.get_assembled() + '\n')
