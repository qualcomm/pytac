# Copyright (c) 2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for the ``installudevrules`` subcommand.

The rule generation is covered directly; the install path is tested with the
privileged commands (``udevadm``, ``sudo``) mocked out, so no test touches the
system's udev configuration.
"""

import sys

import pytest

from pytac import installudevrules
from pytac.cli import build_parser
from pytac.debugboard import Board


def _rule_lines():
    return [
        line
        for line in installudevrules.generate_rules().splitlines()
        if line and not line.startswith("#")
    ]


def test_rules_cover_every_known_board():
    rules = installudevrules.generate_rules()
    for vid, pid in Board.known_boards():
        assert f'ATTR{{idVendor}}=="{vid:04x}", ATTR{{idProduct}}=="{pid:04x}"' in rules


def test_rules_include_bughopper_v2_hidraw():
    assert (
        'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="2341", ATTRS{idProduct}=="b001"'
        in installudevrules.generate_rules()
    )


def test_every_rule_grants_plugdev_and_uaccess():
    lines = _rule_lines()
    # one USB rule per known board plus the Bughopper V2 hidraw rule
    assert len(lines) == len(Board.known_boards()) + 1
    for line in lines:
        assert 'MODE="0660"' in line
        assert 'GROUP="plugdev"' in line
        assert 'TAG+="uaccess"' in line


def test_dry_run_prints_rules_and_touches_nothing(capsys, tmp_path):
    target = tmp_path / "99-pytac.rules"
    installudevrules.install_udev_rules(str(target), dry_run=True)
    assert capsys.readouterr().out == installudevrules.generate_rules()
    assert not target.exists()


def test_install_as_root_writes_file_and_reloads(monkeypatch, tmp_path, capsys):
    target = tmp_path / "99-pytac.rules"
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(installudevrules.os, "geteuid", lambda: 0)
    monkeypatch.setattr(
        installudevrules, "_run", lambda cmd, **kwargs: calls.append(cmd)
    )

    installudevrules.install_udev_rules(str(target))

    assert target.read_text() == installudevrules.generate_rules()
    assert ["udevadm", "control", "--reload-rules"] in calls
    assert ["udevadm", "trigger"] in calls
    assert not any(cmd[0] == "sudo" for cmd in calls)
    assert f"Installed udev rules to {target}" in capsys.readouterr().out


def test_install_unprivileged_escalates_via_sudo(monkeypatch, tmp_path):
    target = tmp_path / "99-pytac.rules"
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(installudevrules.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(
        installudevrules,
        "_run",
        lambda cmd, **kwargs: calls.append((cmd, kwargs.get("input"))),
    )

    installudevrules.install_udev_rules(str(target))

    # the rules are piped to "sudo tee" rather than written directly
    assert not target.exists()
    tee_calls = [c for c in calls if c[0][:2] == ["sudo", "tee"]]
    assert len(tee_calls) == 1
    assert tee_calls[0][0] == ["sudo", "tee", str(target)]
    assert tee_calls[0][1] == installudevrules.generate_rules().encode()
    cmds = [cmd for cmd, _ in calls]
    assert ["sudo", "udevadm", "control", "--reload-rules"] in cmds
    assert ["sudo", "udevadm", "trigger"] in cmds


def test_parser_accepts_installudevrules_on_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    parser = build_parser()
    args = parser.parse_args(["installudevrules", "--dry-run"])
    assert args.mode == "installudevrules"
    assert args.dry_run is True
    assert args.rules_path is None


@pytest.mark.parametrize("platform", ["darwin", "win32"])
def test_parser_rejects_installudevrules_off_linux(monkeypatch, capsys, platform):
    monkeypatch.setattr(sys, "platform", platform)
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["installudevrules"])
    assert "invalid choice" in capsys.readouterr().err
