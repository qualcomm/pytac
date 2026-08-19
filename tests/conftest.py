# Copyright (c) 2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

"""Shared fixtures and helpers for the pytactl test suite.

The tests mock the USB layer (and the underlying GPIO/serial hardware) so that
every config file under ``tac_configs/`` can be loaded through the exact same
code path that ``pytactl.shell`` and ``pytactl.service`` use:
``Board.create_board()``.

A handful of configs are deliberately handled specially (see the maps below):

* EXCLUDED_CONFIGS   - not driven by the config-script path at all, so the suite
                       does not try to load them through FtdiBoard/PsocBoard.
* XFAIL_LOAD         - configs that currently fail to parse/exec. Left unchanged
                       on purpose; tracked as expected failures.
* XFAIL_REQUIRED     - configs that load fine but legitimately omit one or more
                       of powerOn/powerOff/bootToEDL (the README notes that not
                       every board defines every command).
* XFAIL_EXECUTE      - configs whose scripts reference a pin that is disabled in
                       that config, so invoking the quick method raises.
"""

import glob
import json
import os
import shutil
from collections import namedtuple
from unittest.mock import MagicMock

import pytest

import pytactl
from pytactl import debugboard

# Where "pytactl installconfigs" installs the config set by default
# (platformdirs user data dir for pytactl).
CONFIG_DIR = pytactl.INSTALLED_TAC_CONFIG_PATH

# USB vendor/product pairs that Board.create_board() dispatches on.
FTDI_VENDOR = debugboard.Board.ID_VENDOR_FTDI  # 0x0403
FTDI_PRODUCT = debugboard.Board.ID_PRODUCT_FTDI  # 0x6011
QCOM_VENDOR = debugboard.Board.ID_VENDOR_QCOM  # 0x05C6
QCOM_PRODUCT = debugboard.Board.ID_PRODUCT_QCOM  # 0x9302

# Configs that are not loaded through the config-script path and so are not part
# of the data-driven config tests.
EXCLUDED_CONFIGS = {
    # PIC32CX uses a third dispatch path (udev detection + serial-prefix config
    # matching) rather than the FTDI/PSOC USB-descriptor path the data-driven
    # tests model. Covered directly by test_create_board_dispatches_pic32cx.
    "TAC_PIC32CXAuto_54.tcnf": "PIC32CXAuto uses a dedicated dispatch path",
    # Bughopper board: handled by BughopperV1Board/BughopperV2Board (driven over
    # USB control / HID transfers), not by a config script.
    "TAC_FTDI_80.tcnf": "Bughopper board, handled by a dedicated board class",
}

# Configs that currently fail to parse/exec. Intentionally left unchanged.
XFAIL_LOAD = {
    "TAC_FTDI_51.tcnf": "wrong indentation",
    "TAC_FTDI_52.tcnf": "wrong indentation",
    "TAC_FTDI_72.tcnf": "wrong indentation",
    "TAC_FTDI_77.tcnf": "wrong indentation",
}

# Configs that load but do not define all three of powerOn/powerOff/bootToEDL.
XFAIL_REQUIRED = {
    "TAC_FTDI_15.tcnf": "defines bootToEDL only; no powerOn/powerOff",
    "TAC_FTDI_16.tcnf": "no bootToEDL (board without EDL entry)",
    "TAC_FTDI_41.tcnf": "uses spowerOn/bootToSDXEDL variants; no powerOn/bootToEDL",
    "TAC_FTDI_42.tcnf": "empty script (SMART LABEL board defines no functions)",
    "TAC_FTDI_60.tcnf": "defines bootToEDL/bootToUEFI only; no powerOn/powerOff",
    "TAC_PSOC_24.tcnf": "defines bootToEDL variants only; no powerOn/powerOff",
    "TAC_PSOC_31.tcnf": "defines bootToNADEDL/bootToEAPEDL variants; no bootToEDL",
}

# Configs whose powerOn/powerOff/bootToEDL reference a pin that is disabled in
# that config, so the bound quick method raises AttributeError when invoked.
XFAIL_EXECUTE = {
    "TAC_FTDI_23.tcnf": "script uses 'pkey' which is disabled in this config",
    "TAC_FTDI_29.tcnf": "script uses 'battery' which is disabled in this config",
    "TAC_FTDI_56.tcnf": "script uses 'usb1' which is disabled in this config",
    "TAC_FTDI_65.tcnf": "script uses 'usb1' which is disabled in this config",
    "TAC_FTDI_67.tcnf": "script uses 'usb1' which is disabled in this config",
    "TAC_FTDI_69.tcnf": "script uses 'pkey' which is disabled in this config",
    "TAC_FTDI_72.tcnf": "script uses 'battery' which is disabled in this config",
    "TAC_FTDI_73.tcnf": "script uses 'usb1' which is disabled in this config",
}


# Describes how to make Board.create_board() load a particular config file:
# which USB device to fake and which match key to advertise in devicelist.json.
#   platform_type: the value declared inside the .tcnf (FTDI, PSOC, ...)
#   dispatch:      which board class create_board() routes to, "FTDI" or "PSOC".
#                  debugboard only knows two config-matching mechanisms:
#                  FtdiBoard matches by usb_descriptor, PsocBoard by platform_id.
ConfigEntry = namedtuple(
    "ConfigEntry", ["name", "path", "platform_type", "dispatch", "match_value"]
)


def discover_configs():
    """Return the testable ``.tcnf`` config files (excluding special cases)."""
    paths = sorted(glob.glob(os.path.join(CONFIG_DIR, "*.tcnf")))
    return [p for p in paths if os.path.basename(p) not in EXCLUDED_CONFIGS]


def config_params(xfail_map=None):
    """Build pytest.param() entries for every testable config.

    Configs whose basename appears in ``xfail_map`` (basename -> reason) are
    marked xfail(strict=True), so a config that starts passing surfaces as an
    XPASS and prompts the entry to be removed.
    """
    xfail_map = xfail_map or {}
    params = []
    for path in discover_configs():
        base = os.path.basename(path)
        marks = []
        if base in xfail_map:
            marks.append(pytest.mark.xfail(reason=xfail_map[base], strict=True))
        params.append(pytest.param(path, id=base, marks=marks))
    return params


def make_usb_device(vendor, product_id, serial, product_str=""):
    """Build a fake pyusb device exposing the attributes debugboard reads."""
    dev = MagicMock(name="usb_device")
    dev.idVendor = vendor
    dev.idProduct = product_id
    dev.serial_number = serial
    dev.product = product_str
    return dev


@pytest.fixture
def patch_usb_find(monkeypatch):
    """Return a helper that makes ``usb.core.find`` return a given device."""

    def _install(device):
        monkeypatch.setattr(debugboard.usb.core, "find", lambda **kwargs: device)
        return device

    return _install


@pytest.fixture(autouse=True)
def mock_hardware(monkeypatch):
    """Replace every real hardware touch point with harmless fakes.

    - ``GpioAsyncController`` (FTDI GPIO) becomes a MagicMock, so FtdiPort/FtdiPin
      logic runs without a real FTDI chip.
    - ``PsocPort`` (which opens a serial port in __init__) is swapped for a fake.
    - ``sleep`` is neutralised so config scripts with ``delay`` run instantly.
    """
    monkeypatch.setattr(debugboard, "GpioAsyncController", MagicMock())
    monkeypatch.setattr(debugboard, "sleep", lambda *a, **k: None)

    class _FakePsocPort(debugboard.Port):
        def __init__(self, serialid):
            debugboard.Port.__init__(self, None, serialid)
            self.writes = []
            self.calls = []

        def write(self, value, pin=None):
            self.writes.append((value, pin))

        def call_method(self, method, value):
            self.calls.append((method, value))

        def close(self):
            pass

    monkeypatch.setattr(debugboard, "PsocPort", _FakePsocPort)

    class _FakePic32cxPort(debugboard.Port):
        """Stand-in for Pic32cxPort, which otherwise opens a real CDC serial
        port via udev in __init__."""

        def __init__(self, serialid):
            debugboard.Port.__init__(self, None, serialid)
            self.writes = []

        def write(self, value, pin=None):
            self.writes.append((value, pin))

        def close(self):
            pass

    monkeypatch.setattr(debugboard, "Pic32cxPort", _FakePic32cxPort)


@pytest.fixture(scope="session")
def prepared_configs(tmp_path_factory):
    """Build an isolated tac_config dir containing every testable config plus a
    generated ``devicelist.json`` that maps each one to a unique match key.

    Returns ``(config_dir, entries)`` where ``entries`` maps config basename to
    a :class:`ConfigEntry` describing how to load it via ``create_board``.
    """
    dst = tmp_path_factory.mktemp("tac_configs")
    catalog = []
    entries = {}

    # Mirror what "installconfigs" does: install the bundled FTDI Alpaca-Lite
    # config as default.tcnf, the file FtdiBoard falls back to when a device's
    # USB descriptor matches no catalog entry.
    shutil.copy(
        os.path.join(pytactl.PACKAGE_TAC_CONFIG_PATH, "TAC_FTDI_13.tcnf"),
        os.path.join(dst, pytactl.DEFAULT_CONFIG_FILENAME),
    )

    for path in discover_configs():
        base = os.path.basename(path)
        with open(path) as handle:
            cfg = json.load(handle)
        platform_type = cfg.get("platform_type")
        shutil.copy(path, os.path.join(dst, base))

        if platform_type == "PSOC":
            # PsocBoard matches catalog["platform_id"] against the board id read
            # over serial; assign a unique synthetic id we can return from the
            # mocked __get_board_id.
            platform_id = 90000 + len(entries)
            catalog.append(
                {"platform_id": platform_id, "configPath": f"tac_configs/{base}"}
            )
            entries[base] = ConfigEntry(base, path, platform_type, "PSOC", platform_id)
        else:
            # FTDI (and any other FTDI-USB board): FtdiBoard matches
            # catalog["usb_descriptor"] against device.product. Use a unique
            # synthetic descriptor per file.
            descriptor = f"PYTACTL_TEST::{base}"
            catalog.append(
                {"usb_descriptor": descriptor, "configPath": f"tac_configs/{base}"}
            )
            entries[base] = ConfigEntry(base, path, platform_type, "FTDI", descriptor)

    with open(os.path.join(dst, "devicelist.json"), "w") as handle:
        json.dump({"catalog": catalog}, handle)

    return str(dst), entries


def load_board(config_path, config_dir, entries, patch_usb_find, monkeypatch):
    """Load the board for ``config_path`` through Board.create_board, mocking the
    USB device so the config-by-USB-description dispatch selects this config."""
    entry = entries[os.path.basename(config_path)]

    if entry.dispatch == "FTDI":
        device = make_usb_device(
            FTDI_VENDOR, FTDI_PRODUCT, "FTDI_SERIAL", entry.match_value
        )
        patch_usb_find(device)
        return debugboard.Board.create_board("FTDI_SERIAL", config_dir)

    if entry.dispatch == "PSOC":
        device = make_usb_device(QCOM_VENDOR, QCOM_PRODUCT, "PSOC_SERIAL")
        patch_usb_find(device)
        # __get_board_id() talks to the board over a serial console; short-circuit
        # it to the synthetic platform id we registered in devicelist.json.
        monkeypatch.setattr(
            debugboard.PsocBoard,
            "_PsocBoard__get_board_id",
            lambda self: entry.match_value,
        )
        return debugboard.Board.create_board("PSOC_SERIAL", config_dir)

    raise AssertionError(f"unsupported dispatch {entry.dispatch!r}")
