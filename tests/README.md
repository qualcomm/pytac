# pytactl test suite

Tests that every config file under `tac_configs/` can be loaded through the same
code path `pytactl.shell` and `pytactl.service` use — `Board.create_board()` — with
the USB device, GPIO and serial hardware mocked, and that each board exposes the
required quick methods (`powerOn`, `powerOff`, `bootToEDL`).

The code under test lives in the `pytactl` package (`pytactl/debugboard.py` etc.), so
the tests import it as `from pytactl import debugboard`.

## Configs under test

The data-driven tests run over the `.tcnf` files in a `tac_configs/` directory at
the repo root. Only `TAC_FTDI_13.tcnf` ships bundled inside the package
(`pytactl/tac_configs/`); the full config set lives upstream in
[qcom-test-automation-controller](https://github.com/qualcomm/qcom-test-automation-controller)
and is fetched with `pytactl installconfigs`. Populate `tac_configs/` before running
(the `config-loading` CI workflow does this automatically from upstream):

```sh
mkdir -p tac_configs && cp /path/to/upstream/configurations/* tac_configs/
```

## Running

```sh
. ./venv/bin/activate
pip install -r requirements-dev.txt   # installs pytest
python -m pytest
```

The exact pass/xfail counts track the upstream config set under test; a typical
run is in the order of **~184 passed, 1 skipped, 34 xfailed**.

## How it works

The tests are data-driven over every `tac_configs/*.tcnf` file. For each config a
fake USB device is constructed so that `Board.create_board()`'s vendor/product
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

### Tests (`tests/test_config_loading.py`)

| Test | Asserts |
|------|---------|
| `test_config_loads_via_usb_dispatch` | the config parses and builds a board |
| `test_required_functions_available` | `powerOn`/`powerOff`/`bootToEDL` are present and callable |
| `test_required_functions_execute` | invoking the defined functions runs the parsed script end to end |
| `test_quick_method_call_wrapper` | the REST API `QuickMethod.call()` path works |
| `test_ftdi_falls_back_to_default_config` | an unknown FTDI descriptor falls back to `default.tcnf` (the bundled FTDI Alpaca-Lite config, platform_id 13) |

### Dispatch tests (`tests/test_create_board.py`)

`Board.create_board()` routing: no device → `None`, FTDI, PSOC, Bughopper V1,
and Bughopper V2 with/without the optional `hid` module.

## Special-cased configs

These are declared centrally in `tests/conftest.py`, each with a reason. All
`xfail` markers are `strict=True`, so if a config is fixed (or pins enabled) it
surfaces as an **XPASS**, prompting the entry to be removed.

### Excluded from the suite (`EXCLUDED_CONFIGS`)

Not driven by the config-script path:

| Config | Reason |
|--------|--------|
| `TAC_PIC32CXAuto_54.tcnf` | No `bus` section; PIC32CXAuto board type unsupported by `debugboard` |
| `TAC_FTDI_80.tcnf` | Bughopper board, handled by `BughopperV1Board`/`BughopperV2Board` |

### Expected failures (`xfail`)

**Fail to load** (`XFAIL_LOAD`) — genuinely broken, left unchanged:

| Config | Reason |
|--------|--------|
| `TAC_FTDI_20.tcnf` | line-leading `//` comments break script parsing |

**Omit a required function** (`XFAIL_REQUIRED`) — load fine but don't define all
three of `powerOn`/`powerOff`/`bootToEDL` (the README notes not every board
defines every command):

| Config | Reason |
|--------|--------|
| `TAC_FTDI_15.tcnf` | defines `bootToEDL` only; no `powerOn`/`powerOff` |
| `TAC_FTDI_16.tcnf` | no `bootToEDL` |
| `TAC_FTDI_41.tcnf` | uses `spowerOn`/`bootToSDXEDL` variants; no `powerOn`/`bootToEDL` |
| `TAC_FTDI_42.tcnf` | empty script (SMART LABEL board defines no functions) |
| `TAC_FTDI_60.tcnf` | defines `bootToEDL`/`bootToUEFI` only; no `powerOn`/`powerOff` |
| `TAC_PSOC_24.tcnf` | defines `bootToEDL` variants only; no `powerOn`/`powerOff` |
| `TAC_PSOC_31.tcnf` | defines `bootToNADEDL`/`bootToEAPEDL` variants; no `bootToEDL` |

**Fail to execute** (`XFAIL_EXECUTE`) — define the function but its script
references a pin that is `enabled: false` in that config, so the bound method
raises `AttributeError` when invoked:

`TAC_FTDI_16`, `TAC_FTDI_23`, `TAC_FTDI_29`, `TAC_FTDI_56`, `TAC_FTDI_65`,
`TAC_FTDI_67`, `TAC_FTDI_69`, `TAC_FTDI_72`, `TAC_FTDI_73`, `TAC_PSOC_66`.

## Config fixes applied while building the suite

| Config | Fix |
|--------|-----|
| `TAC_FTDI_51`, `TAC_FTDI_77` | space → tab indentation on the `usb3456` lines |
| `TAC_FTDI_52` | indentation fix + added missing `edl`/`uefi`/`fastboot` variable declarations |
| `TAC_FTDI_72` | added missing `edl`/`uefi`/`fastboot` variable declarations |

## Open issues (not addressed here)

- `TAC_FTDI_20` does not load in production either.
- `TAC_PSOC_31` now loads: `parse_script` renames pin commands that are not
  valid Python identifiers (e.g. `12vpoweroff` → `_12vpoweroff`) consistently
  in the script and the pin command they bind to.
- The 10 `XFAIL_EXECUTE` configs would raise `AttributeError` if their
  `powerOn`/etc. were called on real hardware — a config pin-enablement question
  separate from the test work.
