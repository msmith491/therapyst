#!/usr/bin/env python

from collections import namedtuple
from queue import Queue
from uuid import uuid4

Advice = namedtuple("Advice", "cmd error_expected type id")
Rant = namedtuple("Rant", "result error_code advice id")


# Dynamically generate UUID for each Advice Instance
# Rants get their id from their paired Adivce instance
def adviceFactory(cmd="", error_expected=False, type="shell", id=None):
    if id:
        advice = Advice(cmd, error_expected, type, id)
    else:
        advice = Advice(cmd, error_expected, type, str(uuid4()))
    return advice


def rantFactory(result="", error_code="", advice=""):
    rant = Rant(result, error_code, advice, advice.id)
    return rant


class AdviceQueue(Queue):

    def put(self, item, **kwargs):
        if not isinstance(item, Advice):
            raise ValueError("AdviceQueue will only accept Advice objects")
        super().put(item, **kwargs)


class RantQueue(Queue):

    def put(self, item, **kwargs):
        if not isinstance(item, Rant):
            raise ValueError("AdviceQueue will only accept Advice objects")
        super().put(item, **kwargs)

# Low Priority
# class BulkAdvice(dict):

#     def __init__(self):
#         pass


# Low Priority
# class BulkRant(dict):

#     def __init__(self):
#         pass
