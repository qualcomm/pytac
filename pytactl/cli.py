#!/usr/bin/env python3

# Copyright (c) 2025-2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

import logging
import sys
from argparse import ArgumentParser

from . import DEFAULT_CONFIG_REPOSITORY, __version__, default_tac_config_path

logger = logging.getLogger()


def _setup_logging(level):
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def build_parser():
    parser = ArgumentParser(
        prog="pytactl",
        description="Test Automation Controller (TAC/Alpaca) for Qualcomm debug boards.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Options shared by every subcommand.
    base = ArgumentParser(add_help=False)
    base.add_argument("--log-level", default="DEBUG", help="Log level (default: DEBUG)")

    # Options shared by the board-driving subcommands.
    common = ArgumentParser(add_help=False)
    common.add_argument(
        "--serial",
        nargs="+",
        help="Debug board serial number(s)",
    )
    common.add_argument(
        "--tac-config-path",
        default=default_tac_config_path(),
        help="Path to directory with TAC configs (devicelist.json + .tcnf "
        "files). Required for FTDI/PSOC boards; Bughopper boards need no configs. "
        "Defaults to the configs installed by 'installconfigs', else those "
        "bundled with the package.",
    )

    subparsers = parser.add_subparsers(dest="mode", required=True, metavar="COMMAND")

    subparsers.add_parser(
        "list",
        parents=[base],
        help="List connected debug boards and their serial numbers",
    )

    shell = subparsers.add_parser(
        "shell", parents=[base, common], help="Run the interactive shell"
    )
    shell.add_argument(
        "--config-file-path",
        help="Path to a single config file; use for debugging the config file syntax.",
    )

    oneshot = subparsers.add_parser(
        "oneshot", parents=[base, common], help="Run a single command and exit"
    )
    oneshot.add_argument("command", help="Command to run, e.g. bootToEDL")
    oneshot.add_argument(
        "value",
        nargs="?",
        help="Optional integer value for pin commands, e.g. 1",
    )
    oneshot.add_argument(
        "--config-file-path",
        help="Path to a single config file; use for debugging the config file syntax.",
    )

    installconfigs = subparsers.add_parser(
        "installconfigs",
        parents=[base],
        help="Download TAC config files (.tcnf + devicelist.json) from the "
        "config repository",
    )
    installconfigs.add_argument(
        "--config-repository",
        default=DEFAULT_CONFIG_REPOSITORY,
        help="Config repository URL to fetch configs from (default: %(default)s)",
    )
    installconfigs.add_argument(
        "--local-path",
        help="Directory to install configs into (default: the platformdirs "
        "user data directory for pytactl)",
    )
    installconfigs.add_argument(
        "--ref",
        default="HEAD",
        help="Git ref (branch, tag, or commit) to fetch from (default: %(default)s)",
    )
    installconfigs.add_argument(
        "--repository-path",
        default="configurations",
        help="Path within the repository holding the configs (default: %(default)s)",
    )

    service = subparsers.add_parser(
        "service", parents=[base, common], help="Run the REST API service"
    )
    service.add_argument(
        "--hostname",
        default="0.0.0.0",
        help="Host name the server attaches to (default: 0.0.0.0)",
    )
    service.add_argument(
        "--port",
        default=5000,
        type=int,
        help="Port on the host to attach to (default: 5000)",
    )
    return parser


def _list_boards():
    from .debugboard import Board

    boards = Board.list_boards()
    if not boards:
        print("No connected debug boards found.")
        return

    print("Connected debug boards:")
    for board in boards:
        serial = board["serial"] or "<no serial reported>"
        vid_pid = f"{board['vid']:04x}:{board['pid']:04x}"
        print(f"  {board['type']:<14} vid:pid={vid_pid}  serial={serial}")


def _single_board_serial(boards):
    if not boards:
        return None, "no connected debug boards found"

    if len(boards) > 1:
        serials = ", ".join(
            board.get("serial") or "<no serial reported>" for board in boards
        )
        return None, f"multiple connected debug boards found: {serials}"

    serial = boards[0].get("serial")
    if not serial:
        return None, "the connected debug board did not report a serial number"

    return serial, None


def _resolve_serial(args, parser, command):
    if args.serial:
        return args.serial[0]

    if args.config_file_path:
        return None

    from .debugboard import Board

    serial, error = _single_board_serial(Board.list_boards())
    if serial:
        logger.info("Using only connected debug board serial %s", serial)
        return serial

    parser.error(f"{command} requires --serial or --config-file-path ({error})")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.log_level)

    if args.mode == "list":
        _list_boards()
    elif args.mode == "installconfigs":
        from .installconfigs import install_configs

        install_configs(
            args.config_repository,
            args.local_path,
            args.ref,
            args.repository_path,
        )
    elif args.mode == "service":
        if not args.serial:
            parser.error("service requires --serial")
        from .service import run_service

        run_service(args.serial, args.tac_config_path, args.hostname, args.port)
    elif args.mode == "oneshot":
        from .shell import run_oneshot

        serial = _resolve_serial(args, parser, "oneshot")
        run_oneshot(
            args.command,
            serial,
            args.config_file_path,
            args.tac_config_path,
            args.value,
        )
    else:  # shell
        from .shell import run_shell

        serial = _resolve_serial(args, parser, "shell")
        run_shell(serial, args.config_file_path, args.tac_config_path)


if __name__ == "__main__":
    main()
