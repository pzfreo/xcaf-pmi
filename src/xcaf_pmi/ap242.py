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
    mapped = to_haecceity(found, part)
    if strict and mapped["unmapped"]:
        raise NotCarriedOver(mapped["unmapped"])
    # quiddity numbers the STEP's parts itself and needs one named only when there are several.
    geometry = geometry_step(doc)
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
    if strict and details["differences"]:
        raise NotCarriedOver([f"read back differently: {d}" for d in details["differences"]])
    return (written, {"unmapped": mapped["unmapped"], "quiddity": details}) if report else written
