# -*- coding: utf-8 -*-

LLPY16_EXTS = [
    'interrupt'
]

def interrupt(assembler, context, hardware_id, number):
    with assembler.preserve('A'):
        assembler.SET('A', number)
        if isinstance(hardware_id, list):
            hardware_id = '[%s]' % hardware_id[0]
        assembler.HWI(hardware_id)
