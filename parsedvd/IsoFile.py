from __future__ import annotations

import json
import atexit
import subprocess
import vapoursynth as vs
from os import name as os_name
from typing import List, Any

from .utils.spathlib import SPath

from .IsoFileCore import IsoFileCore

__all__ = ['IsoFile']

core = vs.core


class _WinIsoFile(IsoFileCore):
    def _get_mount_path(self) -> SPath:
        if self.iso_path.is_dir():
            return self._mount_folder_path()

        disc = self._get_mounted_disc() or self._mount()

        if not disc:
            raise RuntimeError("IsoFile: Couldn't mount ISO file!")

        return disc / self._subfolder

    def _run_disc_util(self, iso_path: SPath, util: str) -> SPath | None:
        process = subprocess.Popen([
            "PowerShell", fr'{util}-DiskImage -ImagePath "{str(iso_path)}" | Get-Volume | ConvertTo-Json'],
            stdout=subprocess.PIPE
        )

        pbjson, err = process.communicate()

        if err or str(pbjson[:len(util)], 'utf8') == util or pbjson == b'':
            return None
        elif util.lower() == "dismount":
            return SPath('')

        bjson: dict[str, str] = json.loads(str(pbjson, 'utf-8'))

        return SPath(f"{bjson['DriveLetter']}:\\")

    def _get_mounted_disc(self) -> SPath | None:
        return self._run_disc_util(self.iso_path, 'Get')

    def _mount(self) -> SPath | None:
        if (mount := self._run_disc_util(self.iso_path, 'Mount')):
            atexit.register(self._unmount)
        return mount

    def _unmount(self) -> SPath | None:
        return self._run_disc_util(self.iso_path, 'Dismount')


class _LinuxIsoFile(IsoFileCore):
    loop_path: SPath | None = None
    cur_mount: SPath | None = None

    def _get_mount_path(self) -> SPath:
        if self.iso_path.is_dir():
            return self._mount_folder_path()

        disc = self._get_mounted_disc() or self._mount()

        if not disc:
            raise RuntimeError("IsoFile: Couldn't mount ISO file!")

        return disc / self._subfolder

    def _subprun(self, *args: Any) -> str:
        return subprocess.run(list(map(str, args)), capture_output=True, universal_newlines=True).stdout

    def _get_mounted_disc(self) -> SPath | None:
        if not (loop_path := self._subprun("losetup", "-j", self.iso_path).strip().split(":")[0]):
            return self.cur_mount

        self.loop_path = SPath(loop_path)

        if "MountPoints:" in (device_info := self._run_disc_util(self.loop_path, ["info", "-b"], True)):
            if cur_mount := device_info.split("MountPoints:")[1].split("\n")[0].strip():
                self.cur_mount = SPath(cur_mount)

        return self.cur_mount

    def _run_disc_util(self, path: SPath, params: List[str], strip: bool = False) -> str:
        output = self._subprun("udisksctl", *params, str(path))

        return output.strip() if strip else output

    def _mount(self) -> SPath | None:
        if not self.loop_path:
            loop_path = self._run_disc_util(self.iso_path, ["loop-setup", "-f"], True)

            if "mapped file" not in loop_path.lower():
                raise RuntimeError("IsoFile: Couldn't map the ISO file!")

            loop_splits = loop_path.split(" as ")

            self.loop_path = SPath(loop_splits[-1][:-1])

        if "mounted" not in (cur_mount := self._run_disc_util(self.loop_path, ["mount", "-b"], True)).lower():
            return None

        mount_splits = cur_mount.split(" at ")

        self.cur_mount = SPath(mount_splits[-1])

        atexit.register(self._unmount)

        return self.cur_mount

    def _unmount(self) -> bool:
        if not self.loop_path:
            return True
        self._run_disc_util(self.loop_path, ["unmount", "-b", ])
        return bool(self._run_disc_util(self.loop_path, ["loop-delete", "-b", ]))


IsoFile = _WinIsoFile if os_name == 'nt' else _LinuxIsoFile
