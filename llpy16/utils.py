# -*- coding: utf-8 -*-
from functools import update_wrapper

def only_once(func):
    func.__called__ = False
    def wrap(*args, **kwargs):
        if func.__called__:
            return
        else:
            func(*args, **kwargs)
            func.__called__ = True
    update_wrapper(wrap, func)
    return wrap

