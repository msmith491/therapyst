#!/usr/bin/env python

from therapyst.thera import TherapyGroup
from therapyst.data import adviceFactory

COUNT = 200

client_dict = {'Larry': {'ip': '192.168.2.9',
                         'username': 'mss',
                         'password': 'rts'},
               'Larry Jr': {'ip': '192.168.2.10',
                            'username': 'mss',
                            'password': 'rts'}}

tests = TherapyGroup.from_dict(client_dict, name='Larry Clan')

advicelist = [adviceFactory("ls -ahl") for _ in range(COUNT)]

# for member in tests.members:
#     member.install_and_start_daemon()

tests.start()
for advice in advicelist:
    tests.give_advice(advice)
    print({member: rant.id
           for member, rant in tests.hear_rant(advice).items()})
