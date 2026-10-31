"""AP242 STEP to an XCAF document: OCCT reads the geometry (names and colours, no GD&T),
haecceity (``quiddity.pmi``) reads the semantic PMI and its presentation, and ``xcaf.build``
writes that PMI into the document as XCAF GD&T, anchored to OCCT's faces."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_ShapeTool
from quiddity import pmi

from xcaf_pmi import geometry, xcaf


def findings(step: str | Path) -> list[dict[str, Any]]:
    """haecceity's findings on reading the STEP: what it repaired, read leniently or refused.
    ``quiddity.pmi.read`` keeps them only when it refuses, so they come from quiddity's own
    ``pmi read``, which states them all."""
    done = subprocess.run([sys.executable, "-I", "-m", "quiddity", "pmi", "read", str(step)],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        return []
    return json.loads(done.stdout).get("findings", [])


def _parts(step: str | Path) -> list[dict[str, Any]]:
    """haecceity's parts of the STEP, each with its name and number of faces."""
    done = subprocess.run([sys.executable, "-I", "-m", "quiddity", "parts", str(step)],
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise ValueError(f"{step}: quiddity cannot list its parts: {done.stderr.strip()}")
    return json.loads(done.stdout)["parts"]


def _choose(doc: TDocStd_Document, theirs: list[dict[str, Any]], index: int) -> tuple[geometry.Part, int]:
    """haecceity's part ``index`` (of ``theirs``, its parts) among OCCT's shapes, and the index of
    its first face in haecceity's numbering of the file's faces (the faces of the parts before it).

    OCCT's part is the shape with as many faces as haecceity's: by its name where several do, else
    the first that is not an assembly."""
    wanted = theirs[index]
    offset = sum(p["faces"] for p in theirs[:index])
    count = lambda label: geometry.shape_map(XCAFDoc_ShapeTool.GetShape_s(label)).Extent()
    candidates = [label for label in geometry.shapes(doc) if count(label) == wanted["faces"]]
    named = [label for label in candidates if geometry.part_name(label) == wanted["name"]]
    simple = [label for label in candidates if not XCAFDoc_ShapeTool.IsAssembly_s(label)]
    if named or simple or candidates:
        return geometry.Part((named or simple or candidates)[0]), offset
    raise ValueError(f"OCCT read no shape with the {wanted['faces']} faces of haecceity's part {index}")


def to_xcaf(step: str | Path | bytes, part: int | None = None, *, report: bool = False,
            presentation: bool = True) -> TDocStd_Document | tuple[TDocStd_Document, dict[str, Any]]:
    """The STEP as an XCAF document: OCCT's geometry, names and colours, with haecceity's reading
    of the PMI as XCAF GD&T, on every part (or only on part ``part``).

    With ``report`` the result is ``(document, {"unmapped": [...], "findings": [...], "faces":
    [...], "added": {...}})``: what the document could not hold, haecceity's findings, how each
    part's faces were matched to OCCT's ("index", "entity" or "geometry", see
    ``geometry.faces``) and what was added. ``presentation=False`` leaves out the callouts.
    haecceity's refusals raise ``quiddity.PmiError``.
    """
    if isinstance(step, bytes):
        with tempfile.TemporaryDirectory() as folder:
            held = Path(folder) / "part.step"
            held.write_bytes(step)
            return to_xcaf(held, part, report=report, presentation=presentation)
    step = Path(step)
    theirs = _parts(step)
    chosen = range(len(theirs)) if part is None else [part]
    if part is not None and not 0 <= part < len(theirs):
        raise ValueError(f"{step}: no part {part}; the file has {len(theirs)}")
    one = None if len(theirs) == 1 else 0  # quiddity names a part only where there are several
    doc, entity_of = geometry.read_step_faces(step)
    unmapped, methods, added = [], [], {}
    for index in chosen:
        semantic = pmi.read(step, part=None if one is None else index)
        shown = pmi.presentation(step, part=None if one is None else index) if presentation else None
        target, offset = _choose(doc, theirs, index)
        matched = geometry.faces(step, target, entity_of, offset)
        built = xcaf.build(doc, target, semantic, matched["faces"], shown)
        where = "" if len(theirs) == 1 else f"part {index}: "
        unmapped += [f"{where}face {i}: OCCT made no face of it" for i in matched["unmatched"]]
        unmapped += [where + line for line in built["unmapped"]]
        methods.append(matched["method"])
        for kind, n in built["added"].items():
            added[kind] = added.get(kind, 0) + n
    if not report:
        return doc
    found = [f for f in findings(step) if f.get("part") is None or f["part"] in chosen]
    return doc, {"unmapped": unmapped, "findings": found, "faces": methods, "added": added}
