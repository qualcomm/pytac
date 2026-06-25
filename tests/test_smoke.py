# Copyright (c) 2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

"""Minimal smoke tests that confirm the pytest setup itself is functional.

These intentionally stay on the import/CLI-parser path and avoid the hardware
and config-loading code, so they run with no debug board attached. Deeper board
and config coverage lives in the dedicated test suite.
"""

import os

import pytac
from pytac.cli import build_parser


def test_version_is_defined():
    assert isinstance(pytac.__version__, str) and pytac.__version__


def test_package_tac_config_path_points_into_package():
    path = pytac.PACKAGE_TAC_CONFIG_PATH
    assert os.path.basename(path) == "tac_configs"
    assert path.startswith(os.path.dirname(pytac.__file__))
    assert os.path.isdir(path)


def test_parser_dispatches_subcommand():
    parser = build_parser()
    args = parser.parse_args(["list"])
    assert args.mode == "list"
