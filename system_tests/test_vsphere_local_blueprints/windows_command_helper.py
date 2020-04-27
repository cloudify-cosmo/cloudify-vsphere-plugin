########
# Copyright (c) 2016-2020 Cloudify Platform Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from time import sleep

from pyVmomi import vim
from pyVim.connect import SmartConnect, Disconnect
import atexit
import requests


class WindowsCommandHelper(object):
    def __init__(self, logger, host, user, password, port=443):
        self.logger = logger
        self.host = host
        self.user = user
        self.password = password
        self.port = port

        self._si = None
        self._content = None

    @property
    def si(self):
        if not self._si:
            self._si = SmartConnect(
                host=self.host,
                user=self.user,
                pwd=self.password,
                port=int(self.port))
            atexit.register(Disconnect, self._si)
        return self._si

    @property
    def content(self):
        if not self._content:
            self._content = self.si.RetrieveContent()
        return self._content

    def _get_obj_list(self, vimtype):
        container_view = self.content.viewManager.CreateContainerView(
            self.content.rootFolder, vimtype, True
        )
        objects = container_view.view
        container_view.Destroy()
        return objects

    def get_obj_by_name(self, vimtype, name, parent_name=None):
        obj = None
        objects = self._get_obj_list(vimtype)
        for c in objects:
            if c.name.lower() == name.lower()\
                    and (parent_name is None or
                         c.parent.name.lower() == parent_name.lower()):
                obj = c
                break
        return obj

    def run_windows_command(
            self,
            vm_name,
            vm_user,
            vm_password,
            command,
            timeout=300,  # seconds
    ):
        """
        Runs a command in a Windows VM & returns the result
        """
        pm = self.content.guestOperationsManager.processManager
        creds = vim.vm.guest.NamePasswordAuthentication(
            username=vm_user,
            password=vm_password)

        vm = self.get_obj_by_name([vim.VirtualMachine], vm_name)

        ps = vim.vm.guest.ProcessManager.ProgramSpec(
            programPath=r'c:\Windows\System32\cmd.exe',
            arguments=r'/c {cmd} 2>&1 > c:\windows\temp\cfy_test_cmd'.format(
                cmd=command))

        for i in range(timeout // 3):
            try:
                pid = pm.StartProgramInGuest(vm, creds, ps)
                break
            except (
                    vim.fault.InvalidGuestLogin,
                    vim.fault.GuestOperationsUnavailable,
            ) as e:
                self.logger.info("invalid login. Waiting. {}".format(str(e)))
                sleep(3)
        else:
            raise CommandTimeoutError('running', command)

        for i in range(timeout // 3):
            sleep(3)
            procs = {
                proc.pid: proc
                for proc
                in pm.ListProcessesInGuest(vm, creds)
            }
            if procs[pid].endTime:
                break
        else:
            raise CommandTimeoutError('retreiving', command)

        return {
            'output': requests.get(
                self.content.guestOperationsManager.
                fileManager.InitiateFileTransferFromGuest(
                    vm,
                    creds,
                    guestFilePath='c:\\windows\\temp\\cfy_test_cmd',
                ).url,
                verify=False,
            ).text,
            'exit_code': procs[pid].exitCode,
        }


class CommandTimeoutError(Exception):
    """
    Raised when the command took too long to return
    """
