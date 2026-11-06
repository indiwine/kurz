import runpy
import unittest
from unittest import mock

from kurz import runner


class EntryPointTest(unittest.TestCase):
    def test_python_m_kurz_calls_main(self):
        with mock.patch.object(runner, "main") as main:
            runpy.run_module("kurz", run_name="__main__")
        main.assert_called_once_with()

    def test_main_wires_bus_and_loop(self):
        with mock.patch.object(runner, "DBusGMainLoop") as gloop, \
             mock.patch.object(runner.dbus, "SessionBus") as bus, \
             mock.patch.object(runner.dbus.service, "BusName") as bus_name, \
             mock.patch.object(runner, "CurrencyRunner") as cls, \
             mock.patch.object(runner.GLib, "MainLoop") as loop:
            runner.main()
        gloop.assert_called_once_with(set_as_default=True)
        bus_name.assert_called_once_with(runner.SERVICE, bus.return_value, do_not_queue=True)
        cls.assert_called_once_with(bus.return_value)
        loop.return_value.run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
