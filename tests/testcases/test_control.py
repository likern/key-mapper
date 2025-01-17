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


"""Testing the key-mapper-control command"""


import os
import unittest
import collections
from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

from keymapper.state import custom_mapping
from keymapper.config import config
from keymapper.paths import get_config_path
from keymapper.daemon import Daemon
from keymapper.mapping import Mapping
from keymapper.paths import get_preset_path

from tests.test import cleanup, tmp


def import_control():
    """Import the core function of the key-mapper-control command."""
    custom_mapping.empty()

    bin_path = os.path.join(os.getcwd(), 'bin', 'key-mapper-control')

    loader = SourceFileLoader('__not_main_idk__', bin_path)
    spec = spec_from_loader('__not_main_idk__', loader)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.main


control = import_control()


options = collections.namedtuple(
    'options',
    ['command', 'config_dir', 'preset', 'device', 'list_devices', 'key_names']
)


class TestControl(unittest.TestCase):
    def tearDown(self):
        cleanup()

    def test_autoload(self):
        devices = ['device 1234', 'device 2345']
        presets = ['preset', 'bar']
        paths = [
            get_preset_path(devices[0], presets[0]),
            get_preset_path(devices[1], presets[1])
        ]
        config_dir = get_config_path()

        Mapping().save(paths[0])
        Mapping().save(paths[1])

        daemon = Daemon()

        start_history = []
        stop_history = []
        daemon.start_injecting = lambda *args: start_history.append(args)
        daemon.stop = lambda *args: stop_history.append(args)

        config.set_autoload_preset(devices[0], presets[0])
        config.set_autoload_preset(devices[1], presets[1])

        control(options('autoload', None, None, None, False, False), daemon)

        self.assertEqual(len(start_history), 2)
        self.assertEqual(len(stop_history), 1)
        self.assertEqual(start_history[0], (devices[0], os.path.expanduser(paths[0]), config_dir))
        self.assertEqual(start_history[1], (devices[1], os.path.abspath(paths[1]), config_dir))

    def test_autoload_other_path(self):
        devices = ['device 1234', 'device 2345']
        presets = ['preset', 'bar']
        config_dir = os.path.join(tmp, 'foo', 'bar')
        paths = [
            os.path.join(config_dir, 'presets', devices[0], presets[0] + '.json'),
            os.path.join(config_dir, 'presets', devices[1], presets[1] + '.json')
        ]

        Mapping().save(paths[0])
        Mapping().save(paths[1])

        daemon = Daemon()

        start_history = []
        stop_history = []
        daemon.start_injecting = lambda *args: start_history.append(args)
        daemon.stop = lambda *args: stop_history.append(args)

        config.path = os.path.join(config_dir, 'config.json')
        config.load_config()
        config.set_autoload_preset(devices[0], presets[0])
        config.set_autoload_preset(devices[1], presets[1])
        config.save_config()

        control(options('autoload', config_dir, None, None, False, False), daemon)

        self.assertEqual(len(start_history), 2)
        self.assertEqual(len(stop_history), 1)
        self.assertEqual(start_history[0], (devices[0], os.path.expanduser(paths[0]), config_dir))
        self.assertEqual(start_history[1], (devices[1], os.path.abspath(paths[1]), config_dir))

    def test_start_stop(self):
        device = 'device 1234'
        path = '~/a/preset.json'
        config_dir = get_config_path()

        daemon = Daemon()

        start_history = []
        stop_history = []
        stop_all_history = []
        daemon.start_injecting = lambda *args: start_history.append(args)
        daemon.stop_injecting = lambda *args: stop_history.append(args)
        daemon.stop = lambda *args: stop_all_history.append(args)

        control(options('start', None, path, device, False, False), daemon)
        self.assertEqual(len(start_history), 1)
        self.assertEqual(start_history[0], (device, os.path.expanduser(path), config_dir))

        control(options('stop', None, None, device, False, False), daemon)
        self.assertEqual(len(stop_history), 1)
        self.assertEqual(stop_history[0], (device,))

        control(options('stop-all', None, None, None, False, False), daemon)
        self.assertEqual(len(stop_all_history), 1)
        self.assertEqual(stop_all_history[0], ())

    def test_config_not_found(self):
        device = 'device 1234'
        path = '~/a/preset.json'
        config_dir = '/foo/bar'

        daemon = Daemon()

        start_history = []
        stop_history = []
        daemon.start_injecting = lambda *args: start_history.append(args)
        daemon.stop_injecting = lambda *args: stop_history.append(args)

        options_1 = options('start', config_dir, path, device, False, False)
        self.assertRaises(SystemExit, lambda: control(options_1, daemon))

        options_2 = options('stop', config_dir, None, device, False, False)
        self.assertRaises(SystemExit, lambda: control(options_2, daemon))


if __name__ == "__main__":
    unittest.main()
