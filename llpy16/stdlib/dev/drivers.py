# -*- coding: utf-8 -*-
from llpy16.utils import only_once

LLPY16_EXTS = [
    'initialize'
]

LLPY16_DATA = [
    'generic_clock',
    'floppy_drive',
    'generic_keyboard',
    'display_monitor',
    'sleep_chamber',
    'vector_display',
]

generic_clock = 'generic_clock'
floppy_drive = 'floppy_drive'
generic_keyboard = 'generic_keyboard'
display_monitor = 'display_monitor'
sleep_chamber = 'sleep_chamber'
vector_display = 'vectory_display'

GENERIC_CLOCK_ID = (0x12d0, 0xb402)
FLOPPY_DRIVE_ID = (0x4fd5, 0x24c5)
GENERIC_KEYBOARD_ID = (0x30cf, 0x7406)
DISPLAY_MONITOR_ID = (0x7349, 0xf615)
SLEEP_CHAMBER_ID = (0x30e4, 0x1d9d)
VECTOR_DISPLAY_ID = (0x42ba, 0xbf3c)

detections = [
    ('clock_detected', GENERIC_CLOCK_ID[1], generic_clock),
    ('floppy_detected', FLOPPY_DRIVE_ID[1], floppy_drive),
    ('keyboard_detected', GENERIC_KEYBOARD_ID[1], generic_keyboard),
    ('monitor_detected', DISPLAY_MONITOR_ID[1], display_monitor),
    ('chamber_detected', SLEEP_CHAMBER_ID[1], sleep_chamber),
    ('vector_detected', VECTOR_DISPLAY_ID[1], vector_display),
]

@only_once
def initialize(assembler, context):
    with assembler.preserve('A', 'B', 'C', 'X', 'Y', 'Z'):
        _ = context.expand_name
        initialize = _('initialize')
        loop_start = _('loop_start')
        cont = _('continue')
        assembler.JSR(initialize)
        with assembler.label(initialize):
            assembler.HWN('I') # store number of attached hardware in I
            assembler.SET('J', 0)
            assembler.write_label(loop_start) # loop start
            assembler.HWQ('J') # hardware query into ABCXY
            for label, hardware_id, data in detections:
                if assembler.IFE('A', hardware_id): # check if it's a hardware we know
                    assembler.goto_label(_(label)) # jump!
            assembler.write_label(cont) # needed by the jump above
            assembler.ADD('J', 1) # increment the counter
            if assembler.IFE('J', 'I'): # check if we're done
                assembler.return_from_subroutine() # SET PC, POP
            assembler.goto_label(loop_start) # loop again

        # write detection labels
        for label, hardware_id, data in detections:
            with assembler.label(_(label)):
                assembler.SET('[%s]' % _(data), 'J')
                assembler.goto_label(cont)
            # write data labels
            with assembler.label(_(data)):
                assembler.write_instruction('DAT', 0xFFFF)
