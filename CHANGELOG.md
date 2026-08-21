# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0] - 2026-08-21

The first release published to [PyPI](https://pypi.org/project/pytactl/). This
release turns a pair of in-tree scripts into an installable command line tool,
so it carries a number of breaking changes for anyone upgrading from 1.4.

### Breaking

- The project and its command are renamed from `pytac` to `pytactl`. The old
  name collides with an unrelated package on PyPI (Diamond Light Source's
  Python Toolkit for Accelerator Controls), so the project could never be
  published under it. Existing installs must switch to the `pytactl` command,
  and the installed config set moves from the `pytac` per-user data directory
  (`~/.local/share/pytac` on Linux) to `pytactl` - re-run
  `pytactl installconfigs` or copy the old directory over.
- Run modes are now subcommands rather than mutually exclusive flags:
  `pytactl shell`, `pytactl oneshot` and `pytactl service` replace
  `--shell`, `--oneshot` and `--service`. Each subcommand has its own help
  and argument set.
- The flat modules were restructured into an importable `pytactl` package and
  are driven through a single console entry point, replacing the previous
  per-script invocation from a checkout.
- Dependencies are declared in `pyproject.toml` instead of `requirements.txt`,
  which is removed. The `pyudev` dependency is dropped in favour of `pyserial`,
  and `platformdirs` is added.

### Added

- Packaging metadata and a console entry point, making the tool installable
  with `pip` and `pipx` and runnable from anywhere.
- `pytactl list` enumerates connected debug boards with their type and serial
  number, so the value needed for `--serial` is discoverable from the tool
  itself instead of `udevadm` or `lsusb`.
- `pytactl installconfigs` downloads every `.tcnf` file and `devicelist.json`
  from the TAC config repository into a local directory (the per-user data
  directory by default). The `--config-repository`, `--local-path`, `--ref`
  and `--repository-path` flags override the source repository, install
  location, git ref and in-repo path.
- `pytactl oneshot` runs a single command against a board and exits, for use
  in CI jobs, provisioning and other scripted automation.
- Support for the PIC32CX board used on automotive platforms.
- A pytest suite: smoke tests covering the package version, the default config
  path and the CLI parser, plus a CI job that pulls the upstream configs and
  checks that `powerOn`, `powerOff` and `bootToEDL` load and run for each one.
- A `Makefile` with `lint`, `format`, `test` and `install-dev` targets, so
  contributors and CI run the same checks.
- `SECURITY.md` documenting how to report a vulnerability, and a workflow that
  builds and publishes releases to PyPI via Trusted Publishing.

### Changed

- Board detection uses `pyserial`'s `serial.tools.list_ports` instead of
  `pyudev`, which depends on Linux-only `libudev`. Board enumeration, PIC32CX
  detection and serial port resolution now work on macOS and Windows as well
  as Linux.
- `--serial` may be omitted when exactly one board is connected; the tool
  assumes that board, matching how `adb` and `fastboot` behave.
- The default config directory prefers the config set installed by
  `installconfigs` when it is populated, falling back to the configs bundled
  with the package.
- The FTDI board fallback prefers `default.tcnf`, keeping `TAC_FTDI_13.tcnf`
  for the bundled case.
- `ruff` replaces `black`, `isort` and `pylint` for formatting, import
  ordering and linting, collapsing three CI jobs into one.
- The README documents `pipx` installation, the native `hidapi` system
  dependency for Ubuntu/Debian and Fedora, the udev rules needed for
  Bughopper V2 (notably under WSL2), and the `installconfigs` and `oneshot`
  subcommands.

### Fixed

- GPIO commands on Windows: a `0x00` HID report-ID placeholder is prepended to
  each write, since hidapi consumes byte 0 as the report ID. Without it the
  `CMD_GPIO` byte was stripped and the board never rebooted, which went
  unnoticed on Linux/hidraw.
- Config script parsing now handles `//` comments, and pin and function names
  that are not valid Python identifiers (for example `12vpoweroff`), so config
  files can be used unchanged.
- Pins marked as disabled but still referenced by a script are handled without
  losing the name-collision behaviour that keeps disabled pins out.
- `except:` was replaced with `except Exception:` so `KeyboardInterrupt` and
  `SystemExit` are no longer swallowed.

## [1.4] - 2026-06-10

Earlier releases are recorded in the git history and in the
[GitHub releases](https://github.com/qualcomm/pytactl/releases) page.

[2.0]: https://github.com/qualcomm/pytactl/compare/v1.4...v2.0
[1.4]: https://github.com/qualcomm/pytactl/releases/tag/v1.4
