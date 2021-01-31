#!/usr/bin/python3
# -*- coding: utf-8 -*-
# key-mapper - GUI for device specific keyboard mappings
# Copyright (C) 2021 sezanzeb <proxima@hip70890b.de>
#
# This file is part of key-mapper.
#
# key-mapper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# key-mapper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with key-mapper.  If not, see <https://www.gnu.org/licenses/>.


"""Starts injecting keycodes based on the configuration.

https://github.com/LEW21/pydbus/tree/cc407c8b1d25b7e28a6d661a29f9e661b1c9b964/examples/clientserver  # noqa pylint: disable=line-too-long
"""


import os
import subprocess
import json

from pydbus import SystemBus
from gi.repository import GLib

from keymapper.logger import logger
from keymapper.dev.injector import Injector, UNKNOWN
from keymapper.mapping import Mapping
from keymapper.config import config
from keymapper.state import system_mapping
from keymapper.getdevices import get_devices, refresh_devices


BUS_NAME = 'keymapper.Control'


def is_service_running():
    """Check if the daemon is running."""
    try:
        subprocess.check_output(['pgrep', '-f', 'key-mapper-service'])
    except subprocess.CalledProcessError:
        return False
    return True


def get_dbus_interface(fallback=True):
    """Get an interface to start and stop injecting keystrokes.

    Parameters
    ----------
    fallback : bool
        If true, returns an instance of the daemon instead if it cannot
        connect
    """
    msg = (
        'The daemon "key-mapper-service" is not running, mapping keys '
        'only works as long as the window is open. '
        'Try `sudo systemctl start key-mapper`'
    )

    if not is_service_running():
        if not fallback:
            logger.error('Service not running')
            return None

        logger.warning(msg)
        return Daemon()

    bus = SystemBus()
    try:
        interface = bus.get(BUS_NAME)
    except GLib.GError as error:
        logger.debug(error)

        if not fallback:
            logger.error('Failed to connect to the running service')
            return None

        logger.warning(msg)
        return Daemon()

    logger.debug('Connected to the service')
    return interface


class Daemon:
    """Starts injecting keycodes based on the configuration.

    Can be talked to either over dbus or by instantiating it.

    The Daemon may not have any knowledge about the logged in user, so it
    can't read any config files. It has to be told what to do and will
    continue to do so afterwards, but it can't decide to start injecting
    on its own.
    """

    dbus = f"""
        <node>
            <interface name='{BUS_NAME}'>
                <method name='stop_injecting'>
                    <arg type='s' name='device' direction='in'/>
                </method>
                <method name='get_state'>
                    <arg type='s' name='device' direction='in'/>
                    <arg type='i' name='response' direction='out'/>
                </method>
                <method name='start_injecting'>
                    <arg type='s' name='device' direction='in'/>
                    <arg type='s' name='path' direction='in'/>
                    <arg type='s' name='xmodmap_path' direction='in'/>
                    <arg type='b' name='response' direction='out'/>
                </method>
                <method name='stop'>
                </method>
                <method name='hello'>
                    <arg type='s' name='out' direction='in'/>
                    <arg type='s' name='response' direction='out'/>
                </method>
            </interface>
        </node>
    """

    def __init__(self):
        """Constructs the daemon."""
        logger.debug('Creating daemon')
        self.injectors = {}

    def stop_injecting(self, device):
        """Stop injecting the mapping for a single device."""
        if self.injectors.get(device) is None:
            logger.debug(
                'Tried to stop injector, but none is running for device "%s"',
                device
            )
            return

        self.injectors[device].stop_injecting()

    def get_state(self, device):
        """Get the injectors state."""
        injector = self.injectors.get(device)
        return injector.get_state() if injector else UNKNOWN

    def start_injecting(self, device, preset_path, config_dir=None):
        """Start injecting the preset for the device.

        Returns True on success.

        Parameters
        ----------
        device : string
            The name of the device
        preset_path : string
            Path to the preset. The daemon, if started via systemctl, has no
            knowledge of the user and their home path, so the complete
            absolute path needs to be provided here.
        config_dir : string
            Contains xmodmap.json and config.json of the current users session
        """
        # reload the config, since it may have been changed
        if config_dir is not None:
            config_path = os.path.join(config_dir, 'config.json')
            if not os.path.exists(config_path):
                logger.error('"%s" does not exist', config_path)
            config.load_config(config_path)

        if device not in get_devices():
            logger.debug('Devices possibly outdated, refreshing')
            refresh_devices()

        if self.injectors.get(device) is not None:
            self.injectors[device].stop_injecting()

        mapping = Mapping()
        try:
            mapping.load(preset_path)
        except FileNotFoundError as error:
            logger.error(str(error))
            return False

        # Path to a dump of the xkb mappings, to provide more human
        # readable keys in the correct keyboard layout to the service.
        # The service cannot use `xmodmap -pke` because it's running via
        # systemd.
        if config_dir is not None:
            xmodmap_path = os.path.join(config_dir, 'xmodmap.json')
            try:
                with open(xmodmap_path, 'r') as file:
                    xmodmap = json.load(file)
                    logger.debug('Using keycodes from "%s"', xmodmap_path)
                    system_mapping.update(xmodmap)
                    # the service now has process wide knowledge of xmodmap
                    # keys of the users session
            except FileNotFoundError:
                logger.error('Could not find "%s"', xmodmap_path)

        try:
            injector = Injector(device, mapping)
            injector.start_injecting()
            self.injectors[device] = injector
        except OSError:
            # I think this will never happen, probably leftover from
            # some earlier version
            return False

        return True

    def stop(self):
        """Stop all injections."""
        logger.info('Stopping all injections')
        for injector in self.injectors.values():
            injector.stop_injecting()

    def hello(self, out):
        """Used for tests."""
        logger.info('Received "%s" from client', out)
        return out
