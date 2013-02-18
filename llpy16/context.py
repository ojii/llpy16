# -*- coding: utf-8 -*-
import ast
from collections import defaultdict
from contextlib import contextmanager
import os
import imp


class Function(object):
    def __init__(self, name, args, node, deferred=True):
        self.name = name
        self.args = args
        self.node = node
        self.deferred = deferred


class Namespace(object):
    def __init__(self):
        self.constants = {}
        self.functions = {}
        self.extensions = {}
        self.configs = {}
        self.data = {}


class Register(object):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name


class Context(object):
    _sep = '__'

    def __init__(self, paths):
        self._paths = paths
        self._namespaces = defaultdict(Namespace)
        self._current_namespace = ''
        self._modules = []

    # Public API

    def find_import(self, name, assembler):
        if name in self._modules:
            # already imported
            return
        bits = name.split('.')
        for path in self._paths:
            pypath = os.path.join(path, *bits) + '.py'
            llpath = os.path.join(path, *bits) + '.llpy16'
            found = False
            if os.path.exists(pypath):
                module = imp.load_source(name, pypath)
                with self.namespace(name):
                    for name in getattr(module, 'LLPY16_EXTS', []):
                        self.define_extension(name, getattr(module, name))
                    for name in getattr(module, 'LLPY16_CONST', []):
                        self.define_constant(name, getattr(module, name))
                    for name in getattr(module, 'LLPY16_DATA', []):
                        self.define_constant(name, self.expand_name(getattr(module, name)))
                    initialize = getattr(module, getattr(module, 'LLPY16_INIT', '-'), None)
                    if callable(initialize):
                        initialize(assembler, self)
                found = True
            if os.path.exists(llpath):
                with open(llpath) as fobj:
                    return fobj.read()
            if found:
                return
        raise ImportError(name)

    def define_extension(self, name, handler):
        self.current_namespace.extensions[name] = handler

    def get_extension(self, name):
        return self.current_namespace.extensions[name]

    def define_constant(self, name, value):
        self.current_namespace.constants[name] = value

    def get_constant(self, name):
        return self.current_namespace.constants[name]

    def define_function(self, name, args, node, deferred=True):
        expanded_name = self.expand_name(name)
        self.current_namespace.functions[name] = Function(expanded_name, args, node, deferred)
        return expanded_name

    def get_function(self, name):
        return self.current_namespace.functions[name]

    def set_config(self, key, value):
        self.current_namespace.configs[key] = value

    def get_config(self, key):
        return self.current_namespace.configs[key]

    def resolve_function(self, node, assembler):
        name, namespace = self._resolve_name(node.func)
        with self.namespace(namespace):
            try:
                ext = self.get_extension(name)
            except KeyError:
                try:
                    return self.get_function(name)
                except KeyError:
                    raise NameError('%s.%s' % (namespace, name))
            args, kwargs = self._call_to_args_kwargs(node)
            ext(assembler, self, *args, **kwargs)

    def expand_name(self, name):
        return self._current_namespace.replace('.', self._sep) + self._sep + name

    @contextmanager
    def namespace(self, namespace):
        old = self._current_namespace
        self._current_namespace = namespace
        try:
            yield
        finally:
            self._current_namespace = old

    # Private API

    @property
    def current_namespace(self):
        return self._namespaces[self._current_namespace]

    def _resolve_name(self, thing):
        if isinstance(thing, ast.Name):
            name = thing.id
            namespace = self._current_namespace
        elif isinstance(thing, ast.Attribute):
            bits = []
            value = thing
            while isinstance(value, ast.Attribute):
                bits.append(value.attr)
                value = value.value
            if not isinstance(value, ast.Name):
                raise TypeError()
            bits.append(value.id)
            bits.reverse()
            name = bits.pop()
            namespace = '.'.join(bits)
        else:
            raise TypeError(thing)
        return name, namespace

    def _call_to_args_kwargs(self, node):
        def _get_value(thing):
            if isinstance(thing, ast.Str):
                return thing.s
            elif isinstance(thing, ast.Num):
                return thing.n
            elif isinstance(thing, ast.Tuple):
                return tuple(map(_get_value, thing.elts))
            elif isinstance(thing, ast.List):
                return list(map(_get_value, thing.elts))
            elif isinstance(thing, ast.Dict):
                return {_get_value(key): _get_value(value) for key, value in zip(thing.keys, thing.values)}
            else:
                name, namespace = self._resolve_name(thing)
                if name == name.upper() and len(name) == 1 and namespace == self._current_namespace:
                    return Register(name)
                else:
                    with self.namespace(namespace):
                        try:
                            return self.get_constant(name)
                        except KeyError:
                            raise NameError(name)
        args = map(_get_value, node.args)
        kwargs = {keyword.arg: _get_value(keyword.value) for keyword in node.keywords}
        return args, kwargs
