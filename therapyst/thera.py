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

    def test_ips(self):
        pass


class TherapyGroup():

    def __init__(self, members, name=None, member_timeout=30):
        self.name = name if name else uuid4()
        self.members = members
        self._member_set = None
        self._advice_queues = {member: AdviceQueue()
                               for member in self.members}
        self._rant_dicts = {member: {}
                            for member in self.members}
        self.member_threads = []
        self.stop = False
        self._member_timeout = member_timeout

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
        return [member.heartbeat for member in self.members]

    def __contains__(self, key):
        return key in self.member_set

    def _setup_member_threads(self):
        for member in self.members:
            thread = threading.Thread(target=self._member_func,
                                      args=(member, ))
            self.member_threads.append(thread)

    def _member_watch(self):
        member_checkups = {member: time.time() for member in self.members}
        while not self.stop:
            for member, heartbeat in self.heartbeats:
                if (not heartbeat and
                        member_checkups[member] >= self._member_timeout):
                    # TODO needs to be agnostic
                    member.start_daemon_linux()
                elif heartbeat:
                    member_checkups[member] = time.time()

    def _member_func(self, member):
        # TODO: Need to figure out how best to managed the advice queues
        # for each client.  Do I have the therapy group populate the
        # Client advice queues directly, or do I have it pass the advice
        # in the client.send_advice function and just have the TherapyGroup
        # threads calling that?
        advice_queue = self._advice_queues[member]
        rant_dict = self._rant_dicts[member]
        while not self.stop:
            advice = advice_queue.get()
            rant_dict[advice.id] = member.send_and_receive(advice)

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

    def give_advice(self, advice):
        """
        Main entry point for interacting with therapyst
        """
        for member in self.members:
            self._advice_queues[member].put(advice)

    def hear_rant(self, advice):
        return {member.name: self._rant_dicts[advice.id]
                for member in self.members}
