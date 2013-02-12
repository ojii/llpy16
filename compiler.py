import ast
from collections import defaultdict, deque
from contextlib import contextmanager
import os
import sys


def find_source(name):
    path = os.path.join(*name.split('.')) + '.llpy16'
    if os.path.exists(path):
        with open(path) as fobj:
            return fobj.read(), path
    else:
        return None, None


class Counter(object):
    def __init__(self):
        self.value = 0

    def next(self):
        self.value += 1
        return self.value


class Assembler(object):
    REGISTERS = ['A', 'B', 'C',
                 'X', 'Y', 'Z',
                 'I', 'J']

    def __init__(self):
        self._body = []
        self._footer = []
        self._current = self._body
        self._loopstack = deque()
        self._counters = defaultdict(Counter)
        self._names = {}
        self._current_namespace = []
        with self.footer():
            self.goto_label('builtin_halt')
            self.write_label('builtin_halt')
            self.goto_label('builtin_halt')

    def get_assembled(self):
        return '\n'.join(['\n'.join(x) for x in [self._body, self._footer]])

    # Low Level API

    def write_instruction(self, instruction, *args):
        self._current.append('%s %s' % (instruction, ', '.join(map(str, args))))

    def write_label(self, label):
        label = '_'.join(self._current_namespace + [label])
        self._current.append(':%s' % label)

    def goto_label(self, label):
        self.write_instruction('SET', 'PC', label)

    # High Level API

    def define_variable(self, name, value):
        target = self._names
        for bit in self._current_namespace:
            target = target[bit]
        target[name] = value

    # Helpers

    def get_next_counter(self, name):
        return self._counters[name].next()

    def has_namespace(self, name):
        bits = name.split('.')
        tmp = self._names
        for bit in bits:
            if bit in tmp:
                tmp = tmp[bit]
            else:
                return False
        return True

    def get_in_current_namespace(self, name):
        return self.get_current_namespace()[name]

    def get_current_namespace(self):
        target = self._names
        for bit in self._current_namespace:
            target = target[bit]
        return target

    def resolve_nameish(self, node):
        if isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Name):
            name = node.id
            if name in self.REGISTERS:
                return name
            try:
                return self.get_in_current_namespace(name)
            except KeyError:
                raise NameError(name)
        elif isinstance(node, ast.Attribute):
            value = node.value
            namespace = []
            while isinstance(value, ast.Attribute):
                namespace.append(value.attr)
                value = value.value
            if not isinstance(value, ast.Name):
                raise TypeError()
            namespace.append(value.id)
            namespace.reverse()
            with self.namespace(namespace):
                name = node.attr
                try:
                    return self.get_in_current_namespace(name)
                except KeyError:
                    raise NameError(name)
        else:
            raise TypeError()

    # Context managers

    @contextmanager
    def namespace(self, bits):
        tmp = self._names
        for bit in bits:
            if bit not in tmp:
                tmp[bit] = {}
            tmp = tmp[bit]
        old = self._current_namespace
        self._current_namespace = bits
        yield
        self._current_namespace = old

    @contextmanager
    def loop(self, start_label, end_label):
        self._loopstack.append((start_label, end_label))
        yield
        self._loopstack.pop()

    @contextmanager
    def footer(self):
        old = self._current
        self._current = self._footer
        yield
        self._current = old

    # Builtins

    def handle_builtin_halt(self, node):
        self.goto_label('builtin_halt')

    def handle_builtin_memset(self, node, compiler):
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
                left_value = self.resolve_nameish(left)
            except (TypeError, NameError):
                return compiler.error("Invalid left value in memset arg one binop %r" % left, left)
            try:
                right_value = self.resolve_nameish(right)
            except (TypeError, NameError):
                return compiler.error("Invalid right value in memset arg one binop %r" % right, right)
            location_value = "%s+%s" % (left_value, right_value)
        else:
            try:
                location_value = self.resolve_nameish(location)
            except (TypeError, NameError):
                return compiler.error("Invalid location value in memset %r" % location, location)
        self.write_instruction('SET', '[%s]' % location_value, self.resolve_nameish(value))

    def handle_builtin_continue(self, node, compiler):
        if not self._loopstack:
            return compiler.error("Cannot continue outside loop", node)
        start, _ = self._loopstack[-1]
        self.goto_label(start)

    def handle_builtin_break(self, node, compiler):
        if not self._loopstack:
            return compiler.error("Cannot break outside loop", node)
        _, end = self._loopstack[-1]
        self.goto_label(end)

    def handle_builtin_define_enumerate(self, node, compiler):
        value = 0
        for arg in node.args:
            if isinstance(arg, ast.Name):
                self.define_variable(arg.id, value)
            else:
                compiler.error("Invalid argument to builtin_define_enumerate %r, expected name" % arg, arg)
            value += 1


class Compiler(object):
    def __init__(self, assembler, filename=None):
        self.assembler = assembler
        self.failed = False
        self.filename = filename

    def _stderr(self, prefix, msg, node):
        if hasattr(node, 'lineno') and hasattr(node, 'col_offset'):
            info = '%s:%s ' % (node.lineno, node.col_offset)
            if self.filename:
                info = '%s:%s' % (self.filename, info)
        else:
            info = ''
        sys.stderr.write('[%s] %s%s\n' % (prefix, info, msg))

    def error(self, msg, node=None):
        self.failed = True
        self._stderr('ERROR', msg, node)

    def warn(self, msg, node=None):
        self._stderr('WARN', msg, node)

    def compile(self, source):
        node = ast.parse(source)
        self.handle(node)
        return not self.failed

    def handle(self, node):
        handler = getattr(self, 'handle_%s' % node.__class__.__name__, None)
        if handler is None:
            self.warn("Unsupported node %r" % node, node)
        else:
            handler(node)

    def handle_Module(self, node):
        for child in node.body:
            self.handle(child)

    def _assign(self, instruction, node):
        if hasattr(node, 'targets'):
            if len(node.targets) != 1:
                return self.error("Invalid assignment, too many targets.", node)
            target = node.targets[0]
        else:
            target = node.target
        if not isinstance(target, ast.Name):
            return self.error("Invalid assignment, target must be register name.", target)
        register = target.id
        if register not in self.assembler.REGISTERS:
            return self.error("Invalid assignment, target register not found: %s." % register, target)
        try:
            value = self.assembler.resolve_nameish(node.value)
        except TypeError:
            return self.error("Invalid assignment, value type %r not valid." % node.value, node.value)
        except NameError, exc:
            return self.error("Invalid assignment, variable %s not found." % exc.message, node.value)
        self.assembler.write_instruction(instruction, register, value)

    def handle_Assign(self, node):
        self._assign('SET', node)

    def handle_AugAssign(self, node):
        if isinstance(node.op, ast.Add):
            instruction = 'ADD'
        elif isinstance(node.op, ast.Sub):
            instruction = 'SUB'
        elif isinstance(node.op, ast.Mult):
            instruction = 'MUL'
        elif isinstance(node.op, ast.Div):
            instruction = 'DIV'
        elif isinstance(node.op, ast.LShift):
            instruction = 'SHL'
        elif isinstance(node.op, ast.RShift):
            instruction = 'SHR'
        elif isinstance(node.op, ast.BitOr):
            instruction = 'BOR'
        elif isinstance(node.op, ast.BitAnd):
            instruction = 'AND'
        elif isinstance(node.op, ast.BitXor):
            instruction = 'XOR'
        else:
            return self.error("Invalid augmented assignment, operator %r not supported" % node.op, node.op)
        self._assign(instruction, node)

    def handle_Expr(self, node):
        self.handle(node.value)

    def handle_Call(self, node):
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            namespace = []
            value = node.func
            while isinstance(value, ast.Attribute):
                namespace.append(value.attr)
                value = value.value
            if not isinstance(value, ast.Name):
                return self.error("Invalid call func %r, expected name" % node.func, node.func)
            namespace.append(value.id)
            namespace.reverse()
            name = '_'.join(namespace)
        else:
            return self.error("Invalid call func %r, expected name" % node.func, node.func)
        if name.startswith('builtin_'):
            handler = getattr(self.assembler, 'handle_%s' % name, None)
            if handler is None:
                return self.error("Unknown builtin %s" % name, node.func)
            else:
                handler(node, self)
        else:
            self.assembler.write_instruction('JSR', name)

    def handle_FunctionDef(self, node):
        if node.name.startswith('builtin_'):
            return self.error("Invalid function name %s, the 'builtin_' prefix is reserved for builtins" % node.name, node)
        with self.assembler.footer():
            self.assembler.write_label(node.name)
            for child in node.body:
                self.handle(child)
            self.assembler.goto_label('POP')

    def handle_While(self, node):
        num = self.assembler.get_next_counter('loop')
        start_label = 'builtin_loop_%s_start' % num
        end_label = 'builtin_loop_%s_end' % num
        # start label
        self.assembler.write_label(start_label)
        # write the test
        if not isinstance(node.test, ast.Compare):
            self.error("Unexpected test in while loop, expected Compare", node.test)
        if len(node.test.comparators) != 1:
            self.error("Invalid while loop test, only one comparator allowed.", node.test)
        right = node.test.comparators[0]
        try:
            right_value = self.assembler.resolve_nameish(right)
        except TypeError:
            return self.error("Invalid right hand side comparator in while loop test, must number, variable or register", right)
        except NameError:
            return self.error("Invalid right hand side comparator in while loop, variable %s not found." % right.id, right)
        try:
            left_value = self.assembler.resolve_nameish(node.test.left)
        except TypeError:
            return self.error("Invalid left hand side comparator in while loop test, must number, variable or register", right)
        except NameError:
            return self.error("Invalid left hand side comparator in while loop, variable %s not found." % right.id, right)
        if len(node.test.ops) != 1:
            return self.error("Invalid while loop test operator, only one operator may be used", node.test.ops)
        operator = node.test.ops[0]
        if isinstance(operator, ast.NotEq):
            instruction = 'IFE'
        elif isinstance(operator, ast.Eq):
            instruction = 'IFN'
        elif isinstance(operator, ast.Gt):
            instruction = 'IFG'
            left_value, right_value = right_value, left_value
        elif isinstance(operator, ast.Lt):
            instruction = 'IFG'
        else:
            return self.error("Invalid while loop test operator %r, must be NotEq, Eq, Gt or Lt." % operator, operator)
        self.assembler.write_instruction(instruction, left_value, right_value)
        self.assembler.goto_label(end_label)
        # write the body
        with self.assembler.loop(start_label, end_label):
            for child in node.body:
                self.handle(child)
        # write loop
        self.assembler.goto_label(start_label)
        # end label
        self.assembler.write_label(start_label)

    def handle_Import(self, node):
        for alias in node.names:
            if alias.asname:
                self.error("Asname in import not supported", alias)
            name = alias.name
            if not self.assembler.has_namespace(name):
                source, filename = find_source(name)
                if source is None:
                    self.error("Could not find module %s" % name, alias)
                else:
                    with self.assembler.namespace(name.split('.')):
                        compiler = Compiler(self.assembler, filename)
                        if not compiler.compile(source):
                            self.error("Error in imported module %s" % name, alias)


def main():
    assembler = Assembler()
    compiler = Compiler(assembler, sys.argv[1])
    with open(sys.argv[1]) as fobj:
        source = fobj.read()
    success = compiler.compile(source)
    sys.stdout.write(assembler.get_assembled() + '\n')
    if not success:
        sys.exit(1)

if __name__ == '__main__':
    main()
