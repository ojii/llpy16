# -*- coding: utf-8 -*-

LLPY16_EXTS = [
    'interrupt'
]

def interrupt(assembler, context, hardware_id, number):
    with assembler.preserve('A'):
        assembler.SET('A', number)
        assembler.HWI(hardware_id)
