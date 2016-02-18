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

from therapyst.data import adviceFactory, rantFactory, AdviceQueue, RantQueue

LOG = logging.getLogger(__name__)
logging.getLogger("paramiko").setLevel(logging.WARNING)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

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

OS_LINUX = 'linux'
OS_OTHER = 'other'


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
        self.os = None
        self.python_version = None
        self._ssh = None
        self.stop = False
        self.ready = False
        self.heartbeat = None
        self.heartbeat_interval = 5
        self.heartbeater = None
        self.rant_listener = None
        self.rants = {}

    def _get_socket(self, socket_type):
        return self.context.socket(socket_type)

    def _str_to_pyobj(self, string):
        json = simplejson.loads(string)
        return rantFactory(json["result"],
                           json["error_code"],
                           adviceFactory(json["advice"]["cmd"],
                                         json["advice"]["error_expected"],
                                         json["advice"]["type"],
                                         json["advice"]["id"]))

    def start(self):
        LOG.debug("Starting Client Threads")
        self.heartbeater = threading.Thread(
            name="heartbeater", target=self.run_heartbeat)
        self.heartbeater.daemon = True
        self.heartbeater.start()
        LOG.debug("Heartbeater started")
        self.rant_listener = threading.Thread(
            name="rant_listener", target=self.rant_listener_func)
        self.rant_listener.daemon = True
        self.rant_listener.start()
        LOG.debug("rant_listener started")
        self.ready = True
        return self.ready

    def send_advice(self, advice):
        """
        Used for Async sending
        """
        if not self.ready:
            self.start()
        socket = self._get_socket(zmq.REQ)
        socket.connect("{}://{}:{}".format(self.protocol,
                                           self.ip,
                                           self.advice_port))
        socket.send_unicode(simplejson.dumps(advice._asdict()))
        LOG.debug("Sending adviceFactory: {}".format(advice))
        resp = socket.recv_unicode()
        LOG.debug("Recived Response: {}".format(resp))
        if advice.id in resp:
            return True
        else:
            return False

    def send_and_receive(self, advice):
        if not self.send_advice(advice):
            raise IOError("Error occurred during communication with client")
        else:
            return self.get_rant(advice)

    # TODO: This method is broken somehow. The daemon is sending the rant,
    # but this guy isn't populating self.rants.  Likely some exception is killing
    # the thread.
    def rant_listener_func(self):
        socket = self._get_socket(zmq.REP)
        socket.connect("{}://{}:{}".format(self.protocol,
                                           self.ip,
                                           self.rant_port))
        while not self.stop:
            rant = self._str_to_pyobj(socket.recv_unicode())
            LOG.debug("Recieved rant: {}".format(rant.id))
            self.rants[rant.id] = rant
            socket.send_unicode("Recieved rant: {}".format(rant.id))

    def get_rant(self, advice, block=True, poll_interval=None):
        if block:
            while not self.stop:
                try:
                    return self.rants.pop(advice.id)
                except KeyError:
                    LOG.debug("rantFactory id {} not found, sleeping {}".format(
                        advice.id, poll_interval))
                    if poll_interval:
                        sleep(poll_interval)
        else:
            return self.rants.pop(advice.id, None)

    def run_heartbeat(self):
        socket = self._get_socket(zmq.REQ)
        while not self.stop:
            sleep(self.heartbeat_interval)
            socket.connect("{}://{}:{}".format(self.protocol,
                                               self.ip,
                                               self.advice_port))
            heartbeat = adviceFactory("", "", "heartbeat")
            socket.send_unicode(simplejson.dumps(heartbeat))
            resp = socket.recv_unicode()
            rant = self._str_to_pyobj(resp)
            if rant.result != "heartbeat_reply":
                self.heartbeat = False
            else:
                self.heartbeat = True
            # LOG.debug("HEARTBEAT status: {}".format(self.heartbeat))

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
        if not self._dir_exists(REMOTE_VENV):
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
            if not self._dir_exists(REMOTE_DIR):
                self.put_dir(sftp, LOCAL_FOLDER, "")
        finally:
            sftp.close()

    def _install_other(self):
        raise NotImplementedError("Unsupported Host")

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
        try:
            cmd = "python3 -c 'import os; print(os.uname().sysname)'"
            result = self._exec_command(cmd).lower()
        except EnvironmentError:
            cmd = "python -c 'import os; print(os.uname()[0])'"
            result = self._exec_command(cmd).lower()
        if OS_LINUX in result:
            self.os = OS_LINUX
            self._install_linux()
            self._setup_venv()
            self._start_daemon_linux()
        else:
            self.os = 'other'
            self._install_other()
            self._setup_venv()
            self._start_daemon_other()

    def start_daemon(self):
        if not self.os:
            pass
        elif self.os == OS_LINUX:
            self._start_daemon_linux()
        else:
            self._start_daemon_other()

    def _start_daemon_linux(self):
        self._exec_command(" ".join((
            REMOTE_VENV_PYTHON, REMOTE_EXECUTE, "> client.log 2>&1 &")))
        try:
            self._exec_command("ps -ef | grep therapyst | grep -v grep")
        except EnvironmentError:
            raise EnvironmentError(
                "Could not start ClientDaemon process on Client {}".format(
                    self.name))

    def _start_daemon_other(self):
        # TODO Implement non-linux OS compatibility
        raise NotImplementedError("Unsupported Host")


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
        LOG.debug("Starting Listener")
        self.listener = threading.Thread(name="listener", target=self._listen)
        self.listener.start()
        LOG.debug("Starting Replyer")
        self.replyer = threading.Thread(name="replyer", target=self._reply)
        self.replyer.start()
        LOG.debug("Starting {} Worker Threads".format(self.max_threads))
        for thread_num in range(self.max_threads):
            thread = \
                threading.Thread(name="worker-{}".format(thread_num),
                                 target=self._worker_function)
            thread.start()
            self.workers.append(thread)

    def stop_workers(self):
        LOG.debug("Joining Worker Threads")
        self.stop = True
        for thread in self.workers:
            thread.join()

    def _get_socket(self, socket_type):
        return self.context.socket(socket_type)

    def _str_to_pyobj(self, string):
        json = simplejson.loads(string)
        return adviceFactory(json["cmd"],
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
        rant = rantFactory(result, proc.returncode, advice)
        print("Result: {}".format(result))
        return rant

    @staticmethod
    def _handle_heartbeat(advice):
        rant = rantFactory("heartbeat_reply", 0, advice)
        LOG.debug("Heartbeat: {}".format(time()))
        return rant

    def _listen(self):
        # TODO Add zmq.auth authentication to connection
        socket = self._get_socket(zmq.REP)
        socket.bind("{}://0.0.0.0:{}".format(self.protocol, self.advice_port))
        while not self.stop:
            advice = self._str_to_pyobj(socket.recv_unicode())
            if advice.type == "heartbeat":
                rant = self._handle_heartbeat(advice)
                socket.send_unicode(simplejson.dumps(rant._asdict()))
            else:
                self.advice_queue.put(advice)
                socket.send_unicode("Recieved advice {}".format(advice.id))

    def _reply(self):
        socket = self._get_socket(zmq.REQ)
        socket.bind("{}://0.0.0.0:{}".format(self.protocol, self.rant_port))
        while not self.stop:
            rant = self.rant_queue.get()
            LOG.debug("Sending rantFactory: {}".format(rant.id))
            socket.send_unicode(simplejson.dumps(rant._asdict()))
            LOG.debug(socket.recv_unicode())

    def _worker_function(self):
        while not self.stop:
            advice = self.advice_queue.get()
            self.log.debug("Received object: {}".format(advice))
            if advice.type == "shell":
                rant = self._handle_shell(advice)
            else:
                rant = rantFactory("unknown advice", 1, advice)
            self.rant_queue.put(rant)
            self.advice_queue.task_done()


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
