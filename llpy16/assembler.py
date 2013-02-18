# -*- coding: utf-8 -*-
from contextlib import contextmanager


def instruction(value, doc=''):
    def wrap(self, a, b):
        self.write_instruction(value, a, b)
        return True
    wrap.__name__ = value
    wrap.__doc__ = doc
    return wrap

def special(value, doc=''):
    def wrap(self, a):
        self.write_instruction(value, a)
        return True
    wrap.__name__ = value
    wrap.__doc__ = doc
    return wrap

def hexify(thing):
    if isinstance(thing, int):
        return '0x%04x' % thing
    elif thing.isdigit():
        return '0x%04x' % int(thing)
    elif thing[0] == '[' and thing[-1] == ']' and thing[1:-1].isdigit():
        return '[0x%04x]' % int(thing[1:-1])
    return str(thing)


class Assembler(object):
    halt_label = '__halt'
    program_counter = 'PC'
    stack_pop_instruction = 'POP'
    stack_push_instruction = 'PUSH'

    def __init__(self):
        self._current = self._body = []
        self._labels = []
        with self.label(self.halt_label):
            self.goto_label(self.halt_label)

    def get_assembled(self):
        program = self._body + [y for x in self._labels for y in x + ['']]
        return '\n'.join(program)

    # Low Level API

    def write_instruction(self, instruction, *args):
        self._current.append('%s %s' % (instruction, ', '.join(map(hexify, args))))

    def write_label(self, label):
        self._current.append(':%s' % label)

    SET = instruction('SET')
    ADD = instruction('ADD')
    SUB = instruction('SUB')
    MUL = instruction('MUL')
    MLI = instruction('MLI')
    DIV = instruction('DIV')
    DVI = instruction('DVI')
    MOD = instruction('MOD')
    MDI = instruction('MDI')
    AND = instruction('AND')
    BOR = instruction('BOR')
    XOR = instruction('XOR')
    SHR = instruction('SHR')
    ASR = instruction('ASR')
    SHL = instruction('SHL')
    IFE = instruction('IFE')
    IFN = instruction('IFN')
    IFG = instruction('IFG')
    IFA = instruction('IFA')
    IFL = instruction('IFL')
    IFU = instruction('IFU')
    IFB = instruction('IFB')
    IFC = instruction('IFC')
    ADX = instruction('ADX')
    SBX = instruction('SBX')
    STI = instruction('STI')
    STD = instruction('STD')

    JSR = special('JSR')
    INT = special('INT')
    IAG = special('IAG')
    IAS = special('IAS')
    RFI = special('RFI')
    IAQ = special('IAQ')
    HWN = special('HWN')
    HWQ = special('HWQ')
    HWI = special('HWI')

    # High Level API

    @contextmanager
    def label(self, name):
        """
        Define a label and
        """
        old = self._current
        self._current = body = []
        self.write_label(name)
        try:
            yield
            self._labels.append(body)
        finally:
            self._current = old

    @contextmanager
    def preserve(self, *registers):
        for reg in registers:
            self.push_stack(reg)
        yield
        for reg in reversed(registers):
            self.pop_stack(reg)

    def goto_label(self, label):
        self.SET(self.program_counter, label)

    def pop_stack(self, into):
        self.SET(into, self.stack_pop_instruction)

    def push_stack(self, value):
        self.SET(self.stack_push_instruction, value)

    def return_from_subroutine(self):
        self.pop_stack(self.program_counter)
