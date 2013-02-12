import ast
from collections import defaultdict, deque
from contextlib import contextmanager
import os
import sys


STDLIB_PATH = os.path.join(os.path.dirname(__file__), 'stdlib')


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
        self._local_aliases = []
        self._func_sigs = {}
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

    def pop_stack(self, into):
        self.write_instruction('SET', into, 'POP')

    def push_stack(self, value):
        self.write_instruction('SET', 'PUSH', value)

    # High Level API

    def define_variable(self, name, value):
        target = self._names
        for bit in self._current_namespace:
            target = target[bit]
        target[name] = value

    def define_function(self, name, sig):
        name = '_'.join(self._current_namespace + [name])
        self._func_sigs[name] = sig

    def get_func_sig(self, name):
        return self._func_sigs.get(name, None)

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
            try:
                return self.resolve_registerish(name)
            except NameError:
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

    def resolve_registerish(self, register):
        if register in self.REGISTERS:
            return register
        elif register in self._local_aliases:
            return self.REGISTERS[self._local_aliases.index(register)]
        else:
            raise NameError()


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
    def local_aliases(self, aliases):
        # used by function defintions
        old = self._local_aliases
        self._local_aliases = aliases
        yield
        self._local_aliases = old

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
    def __init__(self, assembler, find_paths, filename=None):
        self.assembler = assembler
        self._failed = False
        self._filename = filename
        self._find_paths = find_paths
        self._func_stack = deque()

    def _resolve_func_call_name(self, node):
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            namespace = []
            value = node.func
            while isinstance(value, ast.Attribute):
                namespace.append(value.attr)
                value = value.value
            if not isinstance(value, ast.Name):
                raise TypeError()
            namespace.append(value.id)
            namespace.reverse()
            return '_'.join(namespace)
        else:
            raise TypeError()

    def _find_source(self, name):
        for find_path in self._find_paths:
            path = os.path.join(find_path, *name.split('.')) + '.llpy16'
            if os.path.exists(path):
                with open(path) as fobj:
                    return fobj.read(), path
        return None, None

    def _stderr(self, prefix, msg, node):
        if hasattr(node, 'lineno') and hasattr(node, 'col_offset'):
            info = '%s:%s ' % (node.lineno, node.col_offset)
            if self._filename:
                info = '%s:%s' % (self._filename, info)
        else:
            info = ''
        sys.stderr.write('[%s] %s%s\n' % (prefix, info, msg))

    def error(self, msg, node=None):
        self._failed = True
        self._stderr('ERROR', msg, node)

    def warn(self, msg, node=None):
        self._stderr('WARN', msg, node)

    def compile(self, source):
        node = ast.parse(source)
        self.handle(node)
        return not self._failed

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
        try:
            register = self.assembler.resolve_registerish(target.id)
        except NameError:
            return self.error("Invalid assignment, target register or local alias %s not found" % target.id, target)
        try:
            value = self.assembler.resolve_nameish(node.value)
        except TypeError:
            return self.error("Invalid assignment, value type %r not valid." % node.value, node.value)
        except NameError, exc:
            return self.error("Invalid assignment, variable %s not found." % exc.message, node.value)
        self.assembler.write_instruction(instruction, register, value)

    def _call_assign(self, node):
        # handle an assigment with a function call on the right
        try:
            func_name = self._resolve_func_call_name(node.value)
        except TypeError:
            return self.error("Invalid call func %r, expected name" % node.func, node.func)
        signature = self.assembler.get_func_sig(func_name)
        if signature is None:
            return self.error("Call to undefined function %s" % signature, node)
        num_targets = len(node.targets)
        if num_targets != signature['num_ret_values']:
            return self.error("Function %s has %s return values, but only %s are given" % (func_name, signature['num_ret_values'], num_targets), node)
        # render the call
        self.handle(node.value)
        # pop the stack
        for target in reversed(node.targets):
            try:
                name = self.assembler.resolve_nameish(target)
            except NameError:
                return self.error("Cannot assign to name %r, name not found" % target, target)
            except TypeError:
                return self.error("Cannot assign to type %r" % target, target)
            self.assembler.pop_stack(name)

    def handle_Assign(self, node):
        if isinstance(node.value, ast.Call):
            self._call_assign(node)
        else:
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
        try:
            name = self._resolve_func_call_name(node)
        except TypeError:
            return self.error("Invalid call func %r, expected name" % node.func, node.func)
        if name.startswith('builtin_'):
            handler = getattr(self.assembler, 'handle_%s' % name, None)
            if handler is None:
                return self.error("Unknown builtin %s" % name, node.func)
            else:
                handler(node, self)
        else:
            signature = self.assembler.get_func_sig(name)
            if not signature:
                return self.error("Undefined function %s" % name, node)
            # push args to stack
            if len(node.args) != signature['num_args']:
                return self.error("Function %s must be called with %s arguments, got %s instead" % (signature['num_args'], len(node.args)), node)
            for arg in node.args:
                try:
                    arg_value = self.assembler.resolve_nameish(arg)
                except NameError:
                    return self.error("Function argument %s not found" % arg, arg)
                except TypeError:
                    return self.error("Invalid function argument %s" % arg, arg)
                self.assembler.push_stack(arg_value)
            self.assembler.write_instruction('JSR', name)

    def handle_FunctionDef(self, node):
        if node.name.startswith('builtin_'):
            return self.error("Invalid function name %s, the 'builtin_' prefix is reserved for builtins" % node.name, node)
        num_args = len(node.args.args)
        if num_args > 7:
            return self.error("Function definitions may not take more than seven arguments!")
        with self.assembler.footer():
            self.assembler.write_label(node.name)
            # pop the next goto
            self.assembler.pop_stack('J')
            # unload args
            aliases = []
            for i in range(num_args - 1, -1, -1):
                register = self.assembler.REGISTERS[i]
                self.assembler.pop_stack(register)
                aliases.insert(0, node.args.args[i].id)
            self._func_stack.append({'num_args': num_args, 'num_ret_values': 0})
            with self.assembler.local_aliases(aliases):
                for child in node.body:
                    self.handle(child)
            self.assembler.goto_label('J')
            func_sig = self._func_stack.pop()
            self.assembler.define_function(node.name, func_sig)

    def handle_Return(self, node):
        if isinstance(node.value, ast.Name):
            num_ret_values = 1
            try:
                register = self.assembler.resolve_nameish(node.value)
            except NameError:
                return self.error("Could not resolve name %s" % node.value, node.value)
            self.assembler.push_stack(register)
        elif isinstance(node.value, ast.Tuple):
            num_ret_values = len(node.value.elts)
            for element in node.value.elts:
                try:
                    register = self.assembler.resolve_nameish(element)
                except NameError:
                    return self.error("Could not resolve name %s" % element, element)
                self.assembler.push_stack(register)
        self._func_stack[-1]['num_ret_values'] = num_ret_values


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
                source, filename = self._find_source(name)
                if source is None:
                    self.error("Could not find module %s" % name, alias)
                else:
                    with self.assembler.namespace(name.split('.')):
                        compiler = Compiler(self.assembler, self._find_paths, filename)
                        if not compiler.compile(source):
                            self.error("Error in imported module %s" % name, alias)


def main():
    assembler = Assembler()
    compiler = Compiler(assembler, [STDLIB_PATH, os.path.join(os.path.dirname(__file__), 'examples')], sys.argv[1])
    with open(sys.argv[1]) as fobj:
        source = fobj.read()
    success = compiler.compile(source)
    sys.stdout.write(assembler.get_assembled() + '\n')
    if not success:
        sys.exit(1)

if __name__ == '__main__':
    main()
