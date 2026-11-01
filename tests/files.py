"""The STEP files the tests read: committed under ``fixtures/`` where their terms allow it and
they are small, otherwise fetched once (at a pinned commit, checked by SHA-256) into a cache, or
the test is skipped when they cannot be fetched; with ``XCAF_PMI_REQUIRE_FIXTURES=1`` (as CI runs)
it fails instead. The decompressed copies in the cache are checked against the verified archive
each time, and written again where they differ.

Committed: NIST's CTC-01 with NIST's expected PMI, and three specify-core outputs on Apache-2.0
corpus parts. Fetched from pzfreo/quiddity-rust (Apache-2.0): the other NIST models with their
expected PMI (NIST's models may be used without restriction; they are fetched to keep this
repository small) and four more specify-core outputs; from pzfreo/draftwright-rust (AGPL-3.0,
so not committed here): the editor's CNC-review spindle as Specify wrote it.
"""

from __future__ import annotations

import gzip
import hashlib
import os
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).parent / "fixtures"
QUIDDITY = "https://raw.githubusercontent.com/pzfreo/quiddity-rust/11a540e735606d231c420096f299b15cf6059e03/tests/fixtures/ap242/"
DRAFTWRIGHT = "https://raw.githubusercontent.com/pzfreo/draftwright-rust/cb7395ab0c8ab62d06a5c41165fe5feaf5e7605f/tests/fixtures/samples/"
FETCHED = {
    "nist/nist_ctc_02_asme1_ap242-e2.stp.gz": "07d46072b0c80ea1545392b3c23a33ca50b9c6be76da3a87f8f53c3ecdf59aee",
    "nist/nist_ctc_02.expected.json": "5487746922c7254cba9a775e38f65fd93abae03b3a4e6fdb73cc701d653dfb41",
    "nist/nist_ftc_07_asme1_ap242-e2.stp.gz": "641c42c53a2b5c8ea79d15a99c5ee4fc7d511b9edcbc4970ffa25a7807370af4",
    "nist/nist_ftc_07.expected.json": "efb8bf4e5a09f27d3c357600132c8a87c076aeeeef1454cc0661496144dcfe95",
    "nist/nist_ftc_10_asme1_ap242-e2.stp.gz": "e696490a4ad9a800f0377fe316572fb230509c168e05169d29466f1b1830473f",
    "nist/nist_ftc_10.expected.json": "e3ff11ca826aff4cc68826e9c5f301444e33e0c632a504b9db52c29e3bb1b81b",
    "nist/nist_stc_06_asme1_ap242-e3.stp.gz": "02d32c38a56913bc9959d5577eb69493913362da21294c8b0923a9f56de1c66b",
    "nist/nist_stc_06.expected.json": "ae68e0b14d134cf0b45960c943c9a14acf126fcbdd946a2d10ea7068717d6866",
    "nist/nist_stc_09_asme1_ap242-e4.stp.gz": "40a4a727c7567febeb18493aad1d9f70cc2c46605d13077f50a26c65f20b69fc",
    "nist/nist_stc_09.expected.json": "5bba7b86b0b5a469c260b1e661c9a2a8699f0de5ff39bb03136859b870a9be65",
    "nist/nist_stc_10_asme1_ap242-e2.stp.gz": "f32e71c739bb2e3602bf87835215230f87f0a152dc11c8a1c945df829625cccc",
    "nist/nist_stc_10.expected.json": "18323c3de7bf629dce1ab23783d4744437311167cbd47247dfcda001d4a0c904",
    "specify/bracket_positions.step.gz": "076a487361f2676a87102f6fe64955f77f226cf89b021301cd41312bd5eec23a",
    "specify/string_post_tapped.step.gz": "0a99dd55b6e07885a160130f13c7128c7b76f84b886fbecde3876710231c09fe",
    "specify/nist_ctc_01_merge.step.gz": "213f2d9b7f4913710c08b7dc2e8c927e228e3ca7ee4d5fdcb17e9e24602f6759",
    "specify/assembly_plate_pin.step.gz": "e32d623285ca12bed5059f2f9ab1fadeb81d1f0fd85303c08071f8eea2c64fad",
    "draftwright/spindle_shaft_fit.step.gz": "90d68b756516db5c06ba70219a95bf926359c9db815516c5a40bba50b3f13380",
}
NIST = ["nist_ctc_01_asme1_ap242-e1.stp", "nist_ctc_02_asme1_ap242-e2.stp", "nist_ftc_07_asme1_ap242-e2.stp",
        "nist_ftc_10_asme1_ap242-e2.stp", "nist_stc_06_asme1_ap242-e3.stp", "nist_stc_09_asme1_ap242-e4.stp",
        "nist_stc_10_asme1_ap242-e2.stp"]
SPECIFY = ["spool_fits.step", "thumbwheel_thread_knurl.step", "bolt_thread_knurl.step", "bracket_positions.step",
           "string_post_tapped.step", "nist_ctc_01_merge.step", "assembly_plate_pin.step"]
DRAFTWRIGHT_FILES = ["spindle_shaft_fit.step"]


def _missing(message: str):
    """A test file not to be had: the test is skipped, or fails where every file is required."""
    if os.environ.get("XCAF_PMI_REQUIRE_FIXTURES") == "1":
        pytest.fail(f"{message} (XCAF_PMI_REQUIRE_FIXTURES=1: every test file is required)", pytrace=False)
    pytest.skip(message)


def _cache() -> Path:
    folder = Path(os.environ.get("XCAF_PMI_CACHE") or Path.home() / ".cache" / "xcaf-pmi")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _raw(name: str) -> bytes:
    """A fixture's bytes, as committed or fetched."""
    if (HERE / name).exists():
        return (HERE / name).read_bytes()
    if name not in FETCHED:
        raise KeyError(name)
    held = _cache() / name
    if held.exists() and hashlib.sha256(held.read_bytes()).hexdigest() == FETCHED[name]:
        return held.read_bytes()
    base = DRAFTWRIGHT + name.split("/", 1)[1] if name.startswith("draftwright/") else QUIDDITY + name
    try:
        with urllib.request.urlopen(base, timeout=60) as response:
            data = response.read()
    except OSError as error:
        _missing(f"{name}: not committed (see tests/files.py) and could not be fetched: {error}")
    if hashlib.sha256(data).hexdigest() != FETCHED[name]:
        pytest.fail(f"{name}: fetched bytes do not match the pinned SHA-256")
    held.parent.mkdir(parents=True, exist_ok=True)
    held.write_bytes(data)
    return data


def step(name: str) -> Path:
    """A test STEP by its name (``nist_ctc_01_asme1_ap242-e1.stp``, ``spool_fits.step``), as a file."""
    folder = "nist" if name.startswith("nist_") and "_asme1_" in name else \
        "draftwright" if name in DRAFTWRIGHT_FILES else "specify"
    out = _cache() / "steps" / name
    data = gzip.decompress(_raw(f"{folder}/{name}.gz"))  # the archive is checked by its SHA-256
    if not out.exists() or hashlib.sha256(out.read_bytes()).digest() != hashlib.sha256(data).digest():
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    return out


def expected(name: str) -> dict | None:
    """NIST's expected PMI for a NIST model's STEP, or None for other files."""
    import json

    if not (name.startswith("nist_") and "_asme1_" in name):
        return None
    return json.loads(_raw(f"nist/{'_'.join(name.split('_')[:3])}.expected.json"))
