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


def _quiddity(*args: str) -> subprocess.CompletedProcess:
    """quiddity's own command line, in this interpreter (not isolated: quiddity is found where this
    package found it). Paths are made absolute, so none is taken for an option (quiddity's command
    line takes no ``--``)."""
    return subprocess.run([sys.executable, "-m", "quiddity", *args], capture_output=True, text=True, encoding="utf-8")


def findings(step: str | Path, parts: int = 1) -> list[dict[str, Any]]:
    """haecceity's findings on reading the STEP (each of its ``parts``): what it repaired, read
    leniently or refused. ``quiddity.pmi.read`` keeps them only when it refuses, so they come from
    quiddity's own ``pmi read``, which states them all. Where that fails, a finding says so."""
    out = []
    for part in range(parts):
        done = _quiddity("pmi", "read", str(Path(step).resolve()), *(("--part", str(part)) if parts > 1 else ()))
        try:
            if done.returncode != 0:
                raise ValueError((done.stderr or done.stdout).strip()[:300] or f"exit status {done.returncode}")
            out += json.loads(done.stdout).get("findings", [])
        except ValueError as error:
            out.append({"kind": "warning", "part": part if parts > 1 else None, "entity": None, "ids": [],
                        "detail": f"haecceity's findings could not be read (quiddity pmi read: {error})"})
    return out


def _parts(step: str | Path) -> list[dict[str, Any]]:
    """haecceity's parts of the STEP, each with its name and number of faces (and edges)."""
    done = _quiddity("parts", str(Path(step).resolve()))
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
    [...], "edges": [...], "added": {...}})``: what the document could not hold, haecceity's
    findings, how each part's faces and edges were matched to OCCT's ("index", "entity" or
    "geometry", see ``geometry.faces`` and ``geometry.edges``) and what was added.
    ``presentation=False`` leaves out the callouts.

    Where haecceity refuses a part, or does not read an item (its findings say so), OCCT's own
    reading of that GD&T is taken instead (``xcaf.missing``), with a finding of kind "fallback"
    for each: to_xcaf has all OCCT's reader has, and more.
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
    unmapped, methods, edge_methods, added = [], [], [], {}
    refused: dict[int, pmi.PmiError] = {}
    for index in chosen:
        try:
            semantic = pmi.read(step, part=None if one is None else index)
        except pmi.PmiError as error:
            refused[index] = error
            continue
        shown = pmi.presentation(step, part=None if one is None else index) if presentation else None
        target, offset = _choose(doc, theirs, index)
        matched = geometry.faces(step, target, entity_of, offset)
        used = [item["edge"] for f in semantic["pmi"]["features"] for item in f["value"].get("items", []) if "edge" in item]
        edged = geometry.edges(step, target, entity_of, used, matched["faces"], offset)
        built = xcaf.build(doc, target, semantic, matched["faces"], shown, edged["edges"])
        where = "" if len(theirs) == 1 else f"part {index}: "
        unmapped += [f"{where}face {i}: OCCT made no face of it" for i in matched["unmatched"]]
        unmapped += [f"{where}face {i}: its geometry matches more than one of OCCT's faces ({', '.join(map(str, of))}), "
                     "or one another face matches as well; left unanchored" for i, of in matched["ambiguous"]]
        unmapped += [f"{where}edge {k}: {why}; left unanchored" for k, why in edged["unmatched"]]
        edge_methods.append(edged["method"])
        unmapped += [where + line for line in built["unmapped"]]
        methods.append(matched["method"])
        for kind, n in built["added"].items():
            added[kind] = added.get(kind, 0) + n
    found = [f for f in findings(step, len(theirs)) if f.get("part") is None or f["part"] in chosen]
    if refused:  # quiddity's command line refuses them too: the refusal's own findings instead
        found = [f for f in found if not (f["kind"] == "warning" and (f.get("part") in refused or one is None))]
        found += [f for error in refused.values() for f in getattr(error, "findings", None) or []]
    not_read = [f for f in found if f.get("kind") == "nonconformance" and "not read" in f.get("detail", "")]
    if refused or not_read:
        found += _native(step, doc, theirs, chosen, part, refused, added)
    xcaf.seal(doc)
    if not report:
        return doc
    return doc, {"unmapped": unmapped, "findings": found, "faces": methods, "edges": edge_methods, "added": added}


def _native(step: Path, doc, theirs, chosen, part: int | None, refused: dict, added: dict) -> list[dict[str, Any]]:
    """OCCT's own reading of the GD&T haecceity refused or did not read, added to ``doc``; a
    finding for each part refused and each item taken."""
    from xcaf_pmi.reader import read_document

    native_doc = geometry.read_step(step, gdt=True)
    native, ours = read_document(native_doc, str(step)), read_document(doc, str(step))
    if part is not None:
        # Only the chosen part's: the parts (as the reader lists them) its shapes are.
        target, _ = _choose(doc, theirs, part)
        entries = {xcaf._entry(leaf) for leaf, _, _ in target.leaves}
        mine = {i for i, p in enumerate(native["parts"]) if p["entry"] in entries}
        keep = lambda item: any(r.get("part") in mine for r in item["faces"])
        native = {**native, **{g: [x for x in native[g] if keep(x)] for g in ("datums", "dimensions", "tolerances")}}
    taken = xcaf.missing(ours, native)
    for kind, n in xcaf.adopt(doc, native_doc, native, taken).items():
        added[f"{kind} (OCCT's reading)"] = added.get(f"{kind} (OCCT's reading)", 0) + n
    out = [{"kind": "fallback", "part": index if len(theirs) > 1 else None, "entity": None, "ids": [],
            "detail": f"haecceity refuses the part ({error}); OCCT's own reading of its GD&T is used"}
           for index, error in refused.items()]
    for group, item in [] if refused else taken:  # a part refused: its line says it all
        what = f"datum {item['name']}" if group == "datums" else f"{group[:-1]} {item['type']} {item['value']:g}"
        out.append({"kind": "fallback", "part": None, "entity": group[:-1], "ids": [],
                    "detail": f"{what}: haecceity did not read it; OCCT's own reading of it is used"})
    return out
