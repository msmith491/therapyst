#!/usr/bin/env python

import sys
import logging
import threading
import time

from uuid import uuid4

from therapyst.client import Client
from therapyst.data import AdviceQueue

LOG = logging.getLogger(__name__)
logging.getLogger("paramiko").setLevel(logging.WARNING)

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


class Therapyst():

    """
    """

    def __init__(self, data_struct):
        """
        :param data_struct: Initialization data structure

            data_struct has the following structure

            {therapy_group1:
                 client_name1: {"ip": 1.1.1.1,
                                "username", myuser,
                                "password": mypass},
                 client_name2: {"ip": 1.1.1.2,
                                "username": myuser,
                                "password": mypass}
            therapy_group2:
                 client_name3: {"ip": 1.1.1.3,
                                "username", myuser,
                                "password": mypass},
                 client_name4: {"ip": 1.1.1.4,
                                "username": myuser,
                                "password": mypass}
            }

        """
        self.data_struct = data_struct


class TherapyGroup():

    def __init__(self, members, name=None, member_timeout=30,
                 raise_on_timeout=False):
        self.name = name if name else uuid4()
        self.members = members
        self._member_set = None
        self._advice_queues = {member: AdviceQueue()
                               for member in self.members}
        self._rant_dicts = {member: {}
                            for member in self.members}
        self.member_threads = []
        self.member_watch_thread = None
        self.stop = False
        self._member_timeout = member_timeout
        self._raise_on_timeout = raise_on_timeout

    def add_member(self, new_member):
        self.members.append(new_member)
        self._member_set = None

    def remove_member(self, member_name):
        self.members = [member for member in self.members
                        if member.name != member_name]
        self._member_set = None

    @property
    def member_set(self):
        if not self._member_set:
            self._member_set = set(self.members)
        return self._member_set

    @property
    def heartbeats(self):
        return [(member, member.heartbeat) for member in self.members]

    def __contains__(self, key):
        return key in self.member_set

    def _setup_member_watch(self):
        thread = threading.Thread(target=self._member_watch,
                                  name="member_watch")
        thread.daemon = True
        thread.start()
        self.member_watch_thread = thread

    def _setup_member_threads(self):
        for member in self.members:
            thread = threading.Thread(target=self._member_func,
                                      args=(member, ),
                                      name=member.name)
            thread.daemon = True
            thread.start()
            self.member_threads.append(thread)

    def _member_watch(self):
        """
        Auto restart client daemon processes on remote machines based
        on heartbeats
        """
        member_watch = {member: time.time() for member in self.members}
        while not self.stop:
            for member, heartbeat in self.heartbeats:
                if (not heartbeat and
                        member_watch[member] >= self._member_timeout):
                    if self._raise_on_timeout:
                        raise EnvironmentError(
                            "Member: {} of TherapyGroup: {} timed out after {} "
                            "seconds of not responding to heartbeat "
                            "requests".format(
                                member,
                                self.name,
                                time.time() - member_watch[member]))
                    else:
                        member.start_daemon()
                elif heartbeat:
                    member_watch[member] = time.time()

    def _member_func(self, member):
        advice_queue = self._advice_queues[member]
        rant_dict = self._rant_dicts[member]
        while not self.stop:
            advice = advice_queue.get()
            result = member.send_and_receive(advice)
            rant_dict[advice.id] = result

    @classmethod
    def from_dict(cls, data_struct, name=None):
        """
            {
             client_name1: {"ip": 1.1.1.1,
                            "username", myuser,
                            "password": mypass},
             client_name2: {"ip": 1.1.1.2,
                            "username": myuser,
                            "password": mypass}
            }
        """
        clients = [Client(c['ip'], c['username'], c['password'], name=n)
                   for n, c in data_struct.items()]
        return cls(clients, name=name)

    def start(self):
        self._setup_member_threads()
        self._setup_member_watch()

    def give_advice(self, advice):
        """
        Main entry point for interacting with therapyst
        """
        if not any(self.member_threads):
            self._setup_member_threads()
        if not self.member_watch_thread:
            self._setup_member_watch()
        for member in self.members:
            self._advice_queues[member].put(advice)

    def hear_rant(self, advice):
        while True:
            try:
                return {member.name: self._rant_dicts[member][advice.id]
                        for member in self.members}
            except KeyError:
                pass
