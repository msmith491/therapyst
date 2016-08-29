#!/usr/bin/env python

from therapyst.thera import TherapyGroup
from therapyst.data import adviceFactory


COUNT = 200
ips = "192.168.2.8 192.168.2.9 192.168.2.10".split()
client_dict = {'Larry': {'ip': ips[0],
                         'username': 'mss',
                         'password': 'rts'},
               'Larry Jr': {'ip': ips[1],
                            'username': 'mss',
                            'password': 'rts'},
               'Larry Sr': {'ip': ips[2],
                            'username': 'mss',
                            'password': 'rts'}}

tests = TherapyGroup.from_dict(client_dict, name='Larry Clan')

advicelist = [adviceFactory("ls -ahl") for _ in range(COUNT)]

for member in tests.members:
    member.install_and_start_daemon()

# import time
# start = time.time()
tests.start()
for advice in advicelist:
    tests.give_advice(advice)
    result = {member: rant.id for member, rant in tests.hear_rant(advice).items()}
print([len(elem) for elem in tests._rant_dicts.values()])
# end = time.time()
# print(end - start)
