#!/usr/bin/env python

import sys
import argparse
import os
import subprocess
import shlex
import logging

from uuid import uuid4
from time import sleep, time
import errno
import threading

import zmq
import paramiko
import simplejson

from therapyst.data import Advice, Rant, AdviceQueue, RantQueue, HEARTBEAT

LOG = logging.getLogger(__name__)

RANT_DEFAULT_PORT = 5556
ADVICE_DEFAULT_PORT = 5557
REMOTE_DIR = "therapyst"
REMOTE_BINARY = "/".join(("therapyst", os.path.basename(__file__)))
REMOTE_VENV = "therapyst_venv"
REMOTE_VENV_PYTHON = "/".join((REMOTE_VENV, "bin", "python"))
REMOTE_VENV_PIP = "/".join((REMOTE_VENV, "bin", "pip"))
REMOTE_EXECUTE = "/".join((REMOTE_DIR, REMOTE_BINARY))

LOCAL_FOLDER = os.path.split(os.path.dirname(os.path.abspath(__file__)))[0]

REQUIREMENTS = open("/".join((
    LOCAL_FOLDER, "requirements.txt"))).read().strip().replace("\n", " ")


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
            rant_port=RANT_DEFAULT_PORT,
            advice_port=ADVICE_DEFAULT_PORT,
            protocol="tcp"):
        self.ip = ip
        self.username = username
        self.password = password
        self.name = name if name else self._gen_name()
        self.advice_port = advice_port
        self.rant_port = rant_port
        self.protocol = protocol
        self.context = zmq.Context()
        self.python_version = None
        self._ssh = None
        self.stop = False
        self.heartbeat = None
        self.heartbeat_interval = 5
        self.heartbeater = None
        self.results_listener = None
        self.rants = {}

    def _get_socket(self):
        return self.context.socket(zmq.REQ)

    def start(self):
        self.heartbeater = threading.Thread(
            name="heartbeater", target=self.run_heartbeat)
        self.heartbeater.start()
        self.results_listener = threading.Thread(
            name="results_listener", target=self.results_listener_func)
        self.results_listener.start()

    def send_advice(self, advice):
        socket = self._get_socket()
        socket.connect("{}://{}:{}".format(self.protocol,
                                           self.ip,
                                           self.advice_port))
        socket.send_unicode(simplejson.dumps(advice._asdict()))
        LOG.debug("Sending Advice: {}".format(advice))
        resp = socket.recv_unicode()
        LOG.debug("Recived Response: ()".format(resp))
        if advice.id in resp:
            return True
        else:
            return False

    def get_rant(self, advice, block=True, poll_interval=1):
        if block:
            while True:
                try:
                    return self.rants[advice.id]
                except KeyError:
                    sleep(poll_interval)
        else:
            return self.rants.get(advice.id, None)

    def results_listener_func(self):
        socket = self._get_socket()
        socket.connect("{}://{}:{}".format(self.protocol,
                                           self.ip,
                                           self.advice_port))
        while not self.stop:
            rant = socket.recv_unicode()
            self.rants[rant.id] = rant
            socket.send_unicode("Recieved results: {}".format(rant.id))

    def run_heartbeat(self):
        socket = self._get_socket()
        while not self.stop:
            print(self.heartbeat)
            sleep(self.heartbeat_interval)
            socket.connect("{}://{}:{}".format(self.protocol,
                                               self.ip,
                                               self.advice_port))
            socket.send_unicode(simplejson.dumps(HEARTBEAT))
            resp = simplejson.loads(socket.recv_unicode())
            rant = Rant(resp['result'], resp['error_code'], resp['advice'])
            if rant.result != "heartbeat_reply":
                self.heartbeat = False
            else:
                self.heartbeat = True

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

        self._exec_command("{} install {}".format(REMOTE_VENV_PIP, REQUIREMENTS))
        self._exec_command("{} install -e {}".format(REMOTE_VENV_PIP, REMOTE_DIR))

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
            if walker[0] in ["build", "dist"]:
                continue
            try:
                sftp.mkdir(os.path.join(remotepath, walker[0]))
            except IOError as e:
                print(e)
            for file in walker[2]:
                if file.endswith("egg-info"):
                    continue
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

    def __init__(self, advice_port=ADVICE_DEFAULT_PORT,
                 rant_port=RANT_DEFAULT_PORT, log=LOG, max_threads=10,
                 protocol="tcp"):
        self.advice_port = advice_port
        self.rant_port = rant_port
        self.context = zmq.Context()
        self.log = log
        self.protocol = protocol
        self.max_threads = max_threads
        self.advice_queue = AdviceQueue()
        self.rant_queue = RantQueue()
        self.listener = None
        self.replyer = None
        self.workers = []
        self.stop = False

    def start(self):
        self.listener = threading.Thread(name="listener", target=self._listen)
        self.listener.start()
        self.replyer = threading.Thread(name="replyer", target=self._reply)
        self.replyer.start()
        for thread_num in xrange(self.max_threads):
            thread = \
                threading.Thread(name="worker-{}".format(thread_num),
                                 target=self._worker_function)
            thread.start()
            self.workers.append(thread)

    def stop_workers(self):
        self.stop = True
        for thread in self.workers:
            thread.join()

    def _get_socket(self):
        return self.context.socket(zmq.REP)

    def _json_to_pyobj(self, string):
        json = simplejson.loads(string)
        return Advice(json["cmd"],
                      json["error_expected"],
                      json["type"],
                      json["id"])

    @staticmethod
    def _handle_shell(advice):
        print("Running: {}".format(advice.cmd))
        proc = subprocess.Popen(
            shlex.split(advice.cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
        result = proc.communicate()[0]
        rant = Rant(result, proc.returncode, advice, advice.id)
        print("Result: {}".format(result))
        return rant

    @staticmethod
    def _handle_heartbeat(advice):
        rant = Rant("heartbeat_reply", 0, advice, advice.id)
        print("Heartbeat: {}".format(time()))
        return rant

    def _listen(self):
        # TODO Add zmq.auth authentication to connection
        # TODO Run advice requests in separate threads so the heartbeat
        #      can still be maintained during long running requests
        # TODO SOCKETS ARE NOT THREAD SAFE !!! But Contexts ARE
        socket = self._get_socket()
        socket.bind("{}://0.0.0.0:{}".format(self.protocol, self.advice_port))
        while not self.stop:
            advice = self._json_to_pyobj(socket.recv_unicode())
            self.advice_queue.put(advice)
            socket.send_unicode("Recieved advice {}".format(advice.id))

    def _reply(self):
        socket = self._get_socket()
        socket.bind("{}://0.0.0.0:{}".format(self.protocol, self.rant_port))
        while not self.stop:
            rant = self.rant_queue.get()
            socket.send_unicode(simplejson.dumps(rant._asdict()))
            socket.recv_unicode()

    def _worker_function(self):
        advice = self.advice_queue.get()
        self.log.debug("Received object: {}".format(advice))
        if advice.type == "shell":
            rant = self._handle_shell(advice)
        elif advice.type == "heartbeat":
            rant = self._handle_heartbeat(advice)
        else:
            rant = Rant("unknown advice", 1, advice)
        self.rant_queue.put(rant)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p1", "--port1", action="store",
                        default=ADVICE_DEFAULT_PORT,
                        help="Port number for advice stream to bind to")
    parser.add_argument("-p2", "--port2", action="store",
                        default=RANT_DEFAULT_PORT,
                        help="Port number for rant_stream to bind to")
    args = parser.parse_args()

    daemon = ClientDaemon(advice_port=args.port1, rant_port=args.port2)
    daemon.start()


if __name__ == "__main__":
    sys.exit(main())
