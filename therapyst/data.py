#!/usr/bin/env python

from collections import namedtuple
from queue import Queue
from uuid import uuid4

Advice = namedtuple("Advice", "cmd error_expected type id")
Advice.__new__.__defaults__ = ("", False, "shell", uuid4())

HEARTBEAT = Advice(None, None, "heartbeat")

Rant = namedtuple("Rant", "result error_code advice id")
Rant.__new__.__defaults__ = ("", None, "", uuid4())


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
