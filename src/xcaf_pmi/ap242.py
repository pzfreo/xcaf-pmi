"""An XCAF document straight to AP242 STEP with semantic PMI: its geometry (``geometry_step``),
its GD&T as ``haecceity.pmi/1`` (``to_haecceity``), and haecceity writing the one onto the other
in process (``quiddity.pmi.write``), which reads the result back before returning it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quiddity import pmi

from xcaf_pmi.haecceity import to_haecceity
from xcaf_pmi.reader import geometry_step, open_document, read_document


_GROUPS = {"Attribute": "attributes", "Dimension": "dimensions", "Tolerance": "tolerances", "Note": "notes",
           "Datum": "datums", "DatumTarget": "datum_targets", "General": "general", "Thread": "threads",
           "Knurl": "knurls", "Hole": "holes", "SurfaceTexture": "surface_textures"}


def _refused(mapped: dict[str, Any], message: str, attempt: int) -> list[str]:
    """Drop restored items haecceity's writer refuses: those ``message`` names (``part 0
    Attribute(3): why``), else (``attempt`` 1 on) the restored attributes, else all restored
    items. What was dropped, or nothing if there is nothing restored left to drop."""
    import re

    pmi_ = mapped["document"]["pmi"]
    restored = set(mapped.get("restored", []))
    named = re.findall(r"part \d+ (\w+)\((\d+)\): ([^;]*)", message)
    if not named:
        groups = ["attributes"] if attempt <= 1 else [g for g, v in pmi_.items() if isinstance(v, list)]
        out = []
        for group in groups:
            gone = [x for x in pmi_[group] if isinstance(x, dict) and x.get("id") in restored]
            if gone:
                pmi_[group] = [x for x in pmi_[group] if x not in gone]
                out += [f"{group} {x['id']}: kept by to_xcaf, but haecceity's writer refuses the file with it: "
                        f"{message[:200]}" for x in gone]
        return out
    drop: dict[str, set[int]] = {}
    for kind, index, why in named:
        group = _GROUPS.get(kind)
        if group is None or int(index) >= len(pmi_[group]) or pmi_[group][int(index)]["id"] not in restored:
            return []
        drop.setdefault(group, set()).add(int(index))
    lines = [f"{group[:-1]} {pmi_[group][i]['id']}: kept by to_xcaf, but haecceity's writer refuses it: {why}"
             for (kind, index, why) in named for group in [_GROUPS[kind]] for i in [int(index)]]
    for group, indices in drop.items():
        pmi_[group] = [x for i, x in enumerate(pmi_[group]) if i not in indices]
    return lines


def _edges_on(found: dict[str, Any], part: int, doc, geometry: bytes) -> dict[int, int | None]:
    """haecceity's number, on ``geometry`` (``geometry_step``'s STEP of the document), of each edge
    of part ``part`` (by its index in OCCT's map of the part's edges): haecceity numbers a file's
    edges as the file has them, not as OCCT's map does (``geometry.edge_numbering``). OCCT's
    reading of the file gives each edge's ``edge_curve``; an edge whose reading is not the
    document's (its length and centre differ) has no number."""
    import tempfile

    from OCP.TDF import TDF_Label, TDF_Tool
    from OCP.TCollection import TCollection_AsciiString

    from xcaf_pmi import geometry as g
    from xcaf_pmi.from_step import _choose, _parts

    label = TDF_Label()
    TDF_Tool.Label_s(doc.Main().Data(), TCollection_AsciiString(found["parts"][part]["entry"]), label)
    ours = g.Part(label)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "geometry.step"
        path.write_bytes(geometry)
        again, entity_of = g.read_step_faces(path)
        theirs = _parts(path)
        read, offset = _choose(again, theirs, part)
        numbered, _ = g.edge_numbering(path, offset, len(read.faces))
    # OCCT's writer and reader do not keep every edge (seams, degenerate edges): each of the
    # document's edges is the one edge read with its curve, length and centre.
    number = {e: i for i, e in enumerate(numbered)}
    read_as: dict[tuple, list[int]] = {}
    for j, (_, edge, _) in enumerate(read.edges):
        read_as.setdefault(g.edge_print(edge), []).append(j)
    out = {}
    for k, (_, mine, _) in enumerate(ours.edges):
        same = read_as.get(g.edge_print(mine), [])
        out[k] = number.get(entity_of(read.edges[same[0]][1])) if len(same) == 1 else None
    return out


def _renumber_edges(mapped: dict[str, Any], numbers: dict[int, int | None]) -> list[str]:
    """The PMI's edges (OCCT's indices) as haecceity numbers them on the STEP written; an edge
    with no number is left out of its feature, and an item whose feature is then empty is left
    out, each said so."""
    pmi_ = mapped["document"]["pmi"]
    lines, emptied = [], set()
    for feature in pmi_["features"]:
        items = feature["value"].get("items")
        if not items or not any("edge" in i for i in items):
            continue
        kept = []
        for i in items:
            if "edge" not in i:
                kept.append(i)
            elif numbers.get(i["edge"]) is None:
                lines.append(f"feature {feature['id']}: edge {i['edge']}: not found on the STEP written; left out")
            else:
                kept.append({"edge": numbers[i["edge"]]})
        feature["value"]["items"] = kept
        if not kept:
            emptied.add(feature["id"])
    if emptied:
        import json

        grew = True
        while grew:  # a group of an emptied feature goes with it
            more = {f["id"] for f in pmi_["features"] if f["id"] not in emptied
                    and any(json.dumps(e) in json.dumps(f["value"]) for e in emptied)}
            emptied |= more
            grew = bool(more)
        pmi_["features"] = [f for f in pmi_["features"] if f["id"] not in emptied]
        for group, listed in pmi_.items():
            if isinstance(listed, list) and group not in ("features", "geometry"):
                gone = [x for x in listed if isinstance(x, dict) and any(json.dumps(f) in json.dumps(x) for f in emptied)]
                lines += [f"{group[:-1]} {x.get('id')}: on edges not found on the STEP written; left out" for x in gone]
                pmi_[group] = [x for x in listed if x not in gone]
    return lines


def _edges_checked(written: bytes, mapped: dict[str, Any], part: int | None) -> list[str]:
    """Each edge the PMI written is on, checked against the file haecceity wrote: the edge of its
    number there must be one the file's PMI is on."""
    import tempfile

    from xcaf_pmi import geometry as g
    from xcaf_pmi.from_step import _parts

    sent = sorted({i["edge"] for f in mapped["document"]["pmi"]["features"] for i in f["value"].get("items", [])
                   if "edge" in i})
    if not sent:
        return []
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "written.step"
        path.write_bytes(written)
        theirs = _parts(path)
        index = part or 0
        numbered, _ = g.edge_numbering(path, sum(p["faces"] for p in theirs[:index]), theirs[index]["faces"])
        usage = g.pmi_edges(path)
    # haecceity states how many edges it numbers: as many as the file has, else the file's are
    # not its numbering.
    counted = theirs[index].get("edges") in (None, len(numbered))
    return [f"edge {k}: haecceity's numbering of it on the STEP written cannot be checked; its items may be on "
            "another edge" for k in sent if not (counted and k < len(numbered) and numbered[k] in usage)]


class NotCarriedOver(ValueError):
    """``to_step(..., strict=True)`` found GD&T it could not carry over; ``unmapped`` lists it."""

    def __init__(self, unmapped: list[str]):
        super().__init__("not carried over:\n" + "\n".join(f"  {line}" for line in unmapped))
        self.unmapped = unmapped


def to_step(document: str | Path | bytes | Any, part: int = 0, *, strict: bool = False,
            report: bool = False) -> bytes | tuple[bytes, dict[str, Any]]:
    """The document (a path, its bytes, or an open ``TDocStd_Document``) as AP242 STEP bytes, its
    GD&T as semantic PMI on part ``part``.

    What could not be carried over is never dropped silently: with ``strict`` it raises
    ``NotCarriedOver``, as it does for any difference haecceity finds reading the result back; with ``report`` the result is ``(bytes, {"unmapped": [...], "quiddity":
    {...}})``, quiddity's report holding its read-back ``differences`` and its findings.
    haecceity's refusals raise ``quiddity.PmiError``.
    """
    from OCP.TDocStd import TDocStd_Document

    doc = document if isinstance(document, TDocStd_Document) else open_document(document)
    found = read_document(doc, "<bytes>" if isinstance(document, bytes) else
                          "<document>" if doc is document else str(document))
    if not 0 <= part < len(found["parts"]):
        raise ValueError(f"no part {part}: the document has {len(found['parts'])} (numbered from 0)")
    mapped = to_haecceity(found, part)
    # quiddity numbers the STEP's parts itself and needs one named only when there are several.
    geometry = geometry_step(doc)
    if any("edge" in i for f in mapped["document"]["pmi"]["features"] for i in f["value"].get("items", [])):
        mapped["unmapped"] += _renumber_edges(mapped, _edges_on(found, part, doc, geometry))
    if strict and mapped["unmapped"]:
        raise NotCarriedOver(mapped["unmapped"])
    which = part if len(found["parts"]) > 1 else None
    # Items to_xcaf kept whole that haecceity's writer refuses are left out, and said so: those it
    # names, then the kept attributes (which may restate a kept thread), then all that was kept.
    for attempt in range(4):
        try:
            written, details = pmi.write(geometry, mapped["document"], report=True, part=which)
            break
        except pmi.PmiError as error:
            refused = _refused(mapped, str(error), attempt)
            if not refused:
                raise
            mapped["unmapped"] += refused
            if strict:
                raise NotCarriedOver(mapped["unmapped"]) from error
    mapped["unmapped"] += _edges_checked(written, mapped, which)
    if strict and (details["differences"] or mapped["unmapped"]):
        raise NotCarriedOver([f"read back differently: {d}" for d in details["differences"]] + mapped["unmapped"])
    return (written, {"unmapped": mapped["unmapped"], "quiddity": details}) if report else written
