#!/usr/bin/env python

import sys
import os
import subprocess
import argparse
import time
import shlex
import logging
import simplejson
from collections import namedtuple
from queue import Queue
from uuid import uuid4
import errno

import zmq
import paramiko

LOG = logging.getLogger(__name__)
logging.getLogger("paramiko").setLevel(logging.WARNING)

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

DAEMON_DEFAULT_PORT = 5556
REMOTE_DIR = "therapyst"
REMOTE_BINARY = "therapyst.py"
REMOTE_VENV = "therapyst_venv"
REMOTE_VENV_PYTHON = "/".join((REMOTE_VENV, "bin", "python"))
REMOTE_VENV_PIP = "/".join((REMOTE_VENV, "bin", "pip"))
REMOTE_EXECUTE = "/".join((REMOTE_DIR, REMOTE_BINARY))

LOCAL_FOLDER = os.path.dirname(os.path.abspath(__file__))


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


class Client():

    """
    Object the Therapyst uses to communicate with the ClientDaemon
    """

    def __init__(
            self,
            ip,
            username,
            password,
            name=None,
            connect_port=DAEMON_DEFAULT_PORT):
        self.ip = ip
        self.username = username
        self.password = password
        self.name = name if name else self._gen_name()
        self.connect_port = connect_port
        self.socket = zmq.Context().socket(zmq.REQ)
        self.python_version = None
        self._ssh = None

    def send(self, advice):
        self.socket.connect("tcp://{}:{}".format(self.ip, self.connect_port))
        self.socket.send_pyobj(advice)
        resp = self.socket.recv()
        return resp

    @classmethod
    def from_dict(self, d, name=None):
        return Client(d['ip'], d['password'], name=name)

    @staticmethod
    def _gen_name():
        return str(uuid4())

    def _setup_ssh(self):
        if not self._ssh:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                self.ip,
                username=self.username,
                password=self.password)
            self._ssh = ssh
        return self._ssh

    def _exec_command(self, command, error_expected=False):
        LOG.debug("Running command: {}".format(command))
        ssh = self._setup_ssh()
        _, stdout, stderr = ssh.exec_command(command)
        status = stdout.channel.recv_exit_status()
        if not error_expected and status != 0:
            print(stdout.read().decode(), stderr.read().decode())
            raise EnvironmentError("Exit Status for command {"
                                   "} was nonzero: {}".format(command, status))
        return stdout.read().decode()

    def _dir_exists(self, path):
        sftp = self._setup_ssh().open_sftp()
        try:
            sftp.stat(path)
        except IOError as e:
            if e.errno == errno.ENOENT:
                return False
            raise
        else:
            return True
        finally:
            sftp.close()

    def _setup_venv(self):
        try:
            self._exec_command("python3 --version")
            self.python_version = "3"
        except EnvironmentError:
            try:
                self._exec_command("python2.7 --version")
                self.python_version = "2"
            except EnvironmentError:
                raise EnvironmentError("Need at least python2.7+")

        try:
            self._exec_command("virtualenv {} --python=python{}".format(
                REMOTE_VENV, self.python_version))
        except EnvironmentError:
            raise EnvironmentError("virtualenv package in required")

        self._exec_command("{} install pyzmq paramiko".format(REMOTE_VENV_PIP))

    def _install_linux(self):
        sftp = self._setup_ssh().open_sftp()
        try:
            self.put_dir(sftp, LOCAL_FOLDER, "")
        finally:
            sftp.close()

    @staticmethod
    def put_dir(sftp, localpath, remotepath):
        os.chdir(os.path.split(localpath)[0])
        parent = os.path.split(localpath)[1]
        for walker in os.walk(parent):
            try:
                sftp.mkdir(os.path.join(remotepath, walker[0]))
            except IOError as e:
                print(e)
            for file in walker[2]:
                sftp.put(os.path.join(walker[0], file), os.path.join(
                    remotepath, walker[0], file))

    def install_and_start_daemon(self):
        stdout = self._exec_command("uname -a")
        if "linux" in stdout.lower():
            self._install_linux()
            self._setup_venv()
        else:
            raise ValueError("Unsupported Host")
        self._exec_command(" ".join((
            REMOTE_VENV_PYTHON, REMOTE_EXECUTE, "> client.log 2>&1 &")))

    def __str__(self):
        return "<Client obj:{},{}>".format(self.name, self.ip)


class ClientDaemon():

    """
    Daemon process running on the client
    """

    def __init__(self, bind_port=DAEMON_DEFAULT_PORT, log=LOG):
        self.bind_port = bind_port
        self.socket = zmq.Context().socket(zmq.REP)
        self.log = log

    def _json_to_pyobj(json):
        return Advice(json["cmd"], json["error_expected"], json["shell"])

    def listen(self):
        # TODO Add zmq.auth authentication to connection
        self.socket.bind("tcp://0.0.0.0:{}".format(self.bind_port))
        # self.socket.bind("ipc://backend.ipc")
        while True:
            self.advice = self._json_to_pyobj(self.socket.recv_json())
            self.log.debug("Received object: {}".format(self.advice))
            if self.advice.shell == "bash":
                print("Running: {}".format(self.advice.cmd))
                result = subprocess.check_output(shlex.split(self.advice.cmd))
                print("Result: {}".format(result))
                self.socket.send_unicode("{}".format(result))
            time.sleep(1)


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

Advice = namedtuple("Advice", "cmd error_expected shell")
Advice.__new__.__defaults__ = ("", False, "bash")


Rant = namedtuple("Rant", "result error_code cmd")
Rant.__new__.__defaults__ = ("", None, "")


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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", action="store",
                        help="Port number for daemon to bind to")
    args = parser.parse_args()

    port = args.port if args.port else DAEMON_DEFAULT_PORT

    daemon = ClientDaemon(bind_port=port)
    daemon.listen()


if __name__ == "__main__":
    sys.exit(main())
