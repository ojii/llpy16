# -*- coding: utf-8 -*-

LLPY16_EXTS = [
    'interrupt'
]

def interrupt(assembler, context, hardware_id):
    assembler.HWI(hardware_id)
