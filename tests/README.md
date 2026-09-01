# pytactl test suite

Tests that every config file of the TAC config set can be loaded through the
same code path `pytactl.shell` and `pytactl.service` use — `Board.create_board()` — with
the USB device, GPIO and serial hardware mocked, and that each board exposes the
required quick methods (`powerOn`, `powerOff`, `bootToEDL`). Alongside that,
`tests/test_tacconfig.py` covers the config conversion itself.

The code under test lives in the `pytactl` package (`pytactl/debugboard.py` etc.), so
the tests import it as `from pytactl import debugboard`.

## Configs under test

The data-driven tests run over the `.pinout.json` files of a TAC config set.
`tests/conftest.py` looks for one in three places, in order — the same precedence
`pytactl` itself applies, plus an environment override on top:

1. `$PYTACTL_TAC_CONFIG_DIR`, if set — an explicit override, for distro packagers
   and anyone who unpacks a config set somewhere of their own choosing.
2. `pytactl.INSTALLED_TAC_CONFIG_PATH` — a newer upstream set pulled with
   `pytactl installconfigs`, so the suite tests against that when it exists (the
   `config-loading` CI workflow does exactly this).
3. `pytactl.PACKAGE_TAC_CONFIG_PATH` — the config set vendored in this repository
   under `pytactl/tac_configs/`, which is what a plain checkout tests against.

So a bare `python -m pytest` in a fresh checkout runs the full suite offline, against
the bundled configs. To test against current upstream instead:

```sh
pytactl installconfigs
```

or

```sh
pytactl convertconfigs /path/to/upstream/configurations --output ~/tac-configs
export PYTACTL_TAC_CONFIG_DIR=~/tac-configs
```

If none of the three holds a `.pinout.json` file — a distro build that strips the
bundled configs, say — every config-dependent test **skips** with a reason naming all
three, and the remainder of the suite (imports, CLI parser, config conversion,
`create_board()` dispatch for Bughopper, …) still runs — see
[issue #22](https://github.com/qualcomm/pytactl/issues/22). The handful of tests that
are specifically *about* the vendored set skip on their own marker,
`requires_bundled_configs`, so de-vendoring is not a build failure.

## Running

```sh
. ./venv/bin/activate
pip install -e ".[dev]"
python -m pytest
```

The exact pass/xfail counts track the config set under test; a run against the
bundled set is in the order of **239 passed, 1 skipped, 37 xfailed**. With the
configs stripped, expect roughly **46 passed, 15 skipped**.

## How it works

The tests are data-driven over every `*.pinout.json` file of the config set. For each
config a fake USB device is constructed so that `Board.create_board()`'s vendor/product
dispatch and config-by-USB-description matching select that config:

- **FTDI boards** are matched by `usb_descriptor` against the USB device's
  `product` string. The harness writes a synthetic `devicelist.json` mapping each
  config to a unique descriptor and sets the fake device's `product` to match.
- **PSOC boards** are matched by `platform_id`, normally read from the board over
  a serial console. The harness mocks `PsocBoard.__get_board_id` to return the
  synthetic id registered for that config.

Hardware is replaced with harmless fakes (`mock_hardware` fixture):
`GpioAsyncController` → `MagicMock`, `PsocPort` → in-memory fake, `sleep` → no-op
(so config scripts with `delay` run instantly).

### Config-loading tests (`tests/test_config_loading.py`)

| Test | Asserts |
|------|---------|
| `test_config_loads_via_usb_dispatch` | the config parses and builds a board |
| `test_required_functions_available` | `powerOn`/`powerOff`/`bootToEDL` are present and callable |
| `test_required_functions_execute` | invoking the defined functions runs the parsed script end to end |
| `test_quick_method_call_wrapper` | the REST API `QuickMethod.call()` path works |
| `test_ftdi_falls_back_to_default_config` | an unknown FTDI descriptor falls back to `default.pinout.json` (the bundled FTDI Alpaca-Lite config, platform_id 13) |

### Conversion tests (`tests/test_tacconfig.py`)

Cover `pytactl.tacconfig`, the converter from the upstream config files to the shared
pinout format: the field partition between the pinout file and the UI overlay, the
merge back to a combined config, the shadowed-pin resolution that stands in for the
`enabled` flag the pinout format drops, `devicelist.json` rewriting, directory
conversion (in place, to an output directory, dry run, with the UI overlay, and with a
broken config in the source), and that a board built from each of the three accepted
config shapes binds the same pins.

They also cover the provenance annotation: where it is placed, that it replaces rather
than accumulates, that it is treated as envelope (so it never leaks into a merged config),
that `convertconfigs` reads it from the source checkout but does not restamp an
already-imported set, and that `--no-annotate` leaves it off.

Finally they check the vendored config set itself: every bundled file is a valid pinout
config, no `devicelist.json` entry points at a config the package does not ship, and every
config names the same upstream commit — the one `pytactl/tac_configs/README.md` records,
so the two cannot drift.

### Dispatch tests (`tests/test_create_board.py`)

`Board.create_board()` routing: no device → `None`, FTDI, PSOC, Bughopper V1,
Bughopper V2 with/without the optional `hid` module, and PIC32CX.

## Special-cased configs

These are declared centrally in `tests/conftest.py`, each with a reason. All
`xfail` markers are `strict=True`, so if a config is fixed it surfaces as an
**XPASS**, prompting the entry to be removed.

### Excluded from the suite (`EXCLUDED_CONFIGS`)

Not driven by the config-script path:

| Config | Reason |
|--------|--------|
| `TAC_PIC32CXAuto_54.pinout.json` | PIC32CXAuto uses a dedicated dispatch path (covered by `test_create_board_dispatches_pic32cx`) |
| `TAC_FTDI_80.pinout.json` | Bughopper board, handled by `BughopperV1Board`/`BughopperV2Board` |

### Expected failures (`xfail`)

**Fail to load** (`XFAIL_LOAD`) — genuinely broken upstream, left unchanged:

| Config | Reason |
|--------|--------|
| `TAC_FTDI_51.pinout.json` | wrong indentation |
| `TAC_FTDI_52.pinout.json` | wrong indentation |
| `TAC_FTDI_72.pinout.json` | wrong indentation |
| `TAC_FTDI_77.pinout.json` | wrong indentation |

**Omit a required function** (`XFAIL_REQUIRED`) — load fine but don't define all
three of `powerOn`/`powerOff`/`bootToEDL` (the README notes not every board
defines every command):

| Config | Reason |
|--------|--------|
| `TAC_FTDI_15.pinout.json` | defines `bootToEDL` only; no `powerOn`/`powerOff` |
| `TAC_FTDI_16.pinout.json` | no `bootToEDL` (board without EDL entry) |
| `TAC_FTDI_41.pinout.json` | uses `spowerOn`/`bootToSDXEDL` variants; no `powerOn`/`bootToEDL` |
| `TAC_FTDI_42.pinout.json` | empty script (SMART LABEL board defines no functions) |
| `TAC_FTDI_60.pinout.json` | defines `bootToEDL`/`bootToUEFI` only; no `powerOn`/`powerOff` |
| `TAC_PSOC_24.pinout.json` | defines `bootToEDL` variants only; no `powerOn`/`powerOff` |
| `TAC_PSOC_31.pinout.json` | defines `bootToNADEDL`/`bootToEAPEDL` variants; no `bootToEDL` |

**Fail to execute** (`XFAIL_EXECUTE`) — define the function, but its script drives a
command that no pin in the config defines, so the bound method raises
`AttributeError` when invoked:

`TAC_FTDI_23` (`pkey`), `TAC_FTDI_29` (`battery`), `TAC_FTDI_56`, `TAC_FTDI_65`,
`TAC_FTDI_67`, `TAC_FTDI_73` (`usb1`), `TAC_FTDI_69` (`pkey`). `TAC_FTDI_72` is listed
too, but never gets that far — it fails to load.

## Open issues (not addressed here)

- The `XFAIL_EXECUTE` configs would raise `AttributeError` if their
  `powerOn`/etc. were called on real hardware — an upstream config question
  separate from the test work.
- `TAC_PSOC_31` loads because `parse_script` renames pin commands that are not
  valid Python identifiers (e.g. `12vpoweroff` → `_12vpoweroff`) consistently
  in the script and the pin command they bind to.
