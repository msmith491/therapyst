#!/usr/bin/env python

import sys
import logging

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

            {
             client_name1: {"ip": 1.1.1.1,
                            "password": mypass},
             client_name2: {"ip": 1.1.1.2,
                            "password": mypass}
            }

        """
        self.data_struct = data_struct
        self.clients = [Client.from_dict(d, name=name)
                        for name, d in self.data_struct.viewitems()]

    def test_ips(self):
        pass


class TherapyGroup():

    def __init__(self, members):
        self.members = members
        self.member_set = set(members)

    def add_member(self, new_member):
        self.members.append(new_member)

    def remove_member(self, member_name):
        self.members = [member for member in self.members
                        if member.name != member_name]

    def __contains__(self, key):
        return key in self.member_set
