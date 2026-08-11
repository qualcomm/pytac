# Copyright (c) 2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

import json
import logging
import os
import shutil
import sys
from urllib.parse import urlparse

import requests

from . import (
    DEFAULT_CONFIG_FILENAME,
    DEFAULT_CONFIG_REPOSITORY,
    INSTALLED_TAC_CONFIG_PATH,
    PACKAGE_TAC_CONFIG_PATH,
)

logger = logging.getLogger()

# Default subdirectory in the config repository holding the .tcnf files +
# devicelist.json, and the default git ref to fetch them from.
DEFAULT_REPOSITORY_PATH = "configurations"
DEFAULT_REF = "HEAD"

# The synthesized FTDI Alpaca-Lite config shipped with the package. It has no
# upstream .tcnf file, so we copy it into the install directory as default.tcnf.
_BUNDLED_DEFAULT = os.path.join(PACKAGE_TAC_CONFIG_PATH, "TAC_FTDI_13.tcnf")


def _parse_owner_repo(repository_url):
    """Extract (owner, repo) from a GitHub repository URL."""
    path = urlparse(repository_url).path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    parts = path.split("/")
    if len(parts) < 2:
        raise ValueError(
            f"Cannot parse owner/repo from repository URL: {repository_url}"
        )
    return parts[0], parts[1]


def _list_config_files(owner, repo, repository_path, ref):
    """Return [(name, download_url)] for every .tcnf and devicelist.json."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{repository_path}"
    resp = requests.get(api_url, params={"ref": ref}, timeout=30)
    resp.raise_for_status()
    files = []
    for entry in resp.json():
        name = entry.get("name", "")
        if entry.get("type") == "file" and (
            name.endswith(".tcnf") or name == "devicelist.json"
        ):
            files.append((name, entry["download_url"]))
    return files


def _download(url, dest):
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        f.write(resp.content)


def _patch_devicelist(path):
    """Normalise configPath entries to the installed config filenames.

    Upstream leaves configPath empty for boards that rely on the generated
    default FTDI config; point those at the default.tcnf we install. Other
    entries use repository-relative paths (e.g. ../../configurations/X.tcnf),
    but every config is installed flat into one directory, so strip them down to
    the bare filename. Returns the number of entries patched.
    """
    with open(path) as f:
        device_list = json.load(f)
    patched = 0
    for entry in device_list.get("catalog", []):
        config_path = entry.get("configPath")
        if not config_path:
            entry["configPath"] = DEFAULT_CONFIG_FILENAME
            patched += 1
        elif config_path != os.path.basename(config_path):
            entry["configPath"] = os.path.basename(config_path)
            patched += 1
    with open(path, "w") as f:
        json.dump(device_list, f, indent=4)
    return patched


def install_configs(
    config_repository=None, local_path=None, ref=None, repository_path=None
):
    """Download TAC config files and install them into ``local_path``.

    Fetches every ``.tcnf`` and ``devicelist.json`` from ``repository_path`` (at
    git ``ref``) of ``config_repository``, copies the bundled FTDI Alpaca-Lite
    config in as ``default.tcnf``, and rewrites empty ``configPath`` entries in
    ``devicelist.json`` to point at it.
    """
    config_repository = config_repository or DEFAULT_CONFIG_REPOSITORY
    local_path = local_path or INSTALLED_TAC_CONFIG_PATH
    ref = ref or DEFAULT_REF
    repository_path = repository_path or DEFAULT_REPOSITORY_PATH

    owner, repo = _parse_owner_repo(config_repository)
    os.makedirs(local_path, exist_ok=True)

    logger.info(
        "Fetching config list from %s/%s/%s at %s",
        owner,
        repo,
        repository_path,
        ref,
    )
    files = _list_config_files(owner, repo, repository_path, ref)
    if not files:
        logger.error("No .tcnf files or devicelist.json found in %s", config_repository)
        sys.exit(1)

    has_devicelist = False
    for name, url in files:
        logger.info("Downloading %s", name)
        _download(url, os.path.join(local_path, name))
        if name == "devicelist.json":
            has_devicelist = True

    shutil.copyfile(_BUNDLED_DEFAULT, os.path.join(local_path, DEFAULT_CONFIG_FILENAME))
    logger.info("Installed %s", DEFAULT_CONFIG_FILENAME)

    if has_devicelist:
        patched = _patch_devicelist(os.path.join(local_path, "devicelist.json"))
        logger.info("Normalised %d configPath entries in devicelist.json", patched)
    else:
        logger.warning("devicelist.json not found in repository; not patched")

    print(f"Installed {len(files) + 1} TAC config files to {local_path}")
