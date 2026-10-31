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


def to_step(document: str | Path | bytes | Any, part: int | None = None, *, strict: bool = False,
            report: bool = False) -> bytes | tuple[bytes, dict[str, Any]]:
    """The document (a path, its bytes, or an open ``TDocStd_Document``) as AP242 STEP bytes, the
    GD&T of every part (or only of part ``part``) as semantic PMI.

    What could not be carried over is never dropped silently: with ``strict`` it raises
    ``NotCarriedOver``, as it does for any difference haecceity finds reading the result back;
    with ``report`` the result is ``(bytes, {"unmapped": [...], "quiddity": {...},
    "presentation": {...}})``, quiddity's report holding its read-back ``differences`` and its
    findings (for a document of several parts, those of all, and each part's in ``parts``), and
    ``presentation`` the document's own callouts and saved views as ``haecceity.presentation/1``
    (which quiddity 0.4 cannot yet write in place of its layout). haecceity's refusals raise
    ``quiddity.PmiError``.
    """
    from OCP.TDocStd import TDocStd_Document

    doc = document if isinstance(document, TDocStd_Document) else open_document(document)
    found = read_document(doc, "<bytes>" if isinstance(document, bytes) else
                          "<document>" if doc is document else str(document))
    several = len(found["parts"]) > 1
    if part is not None:
        chosen = [part]
    else:
        # Each part with GD&T of its own, written one after the other onto the same STEP.
        chosen = [i for i in range(len(found["parts"])) if _has_pmi(to_haecceity(found, i))] or [0]
    written = geometry_step(doc)
    unmapped, reports, presentation = [], [], None
    for index in chosen:
        mapped = to_haecceity(found, index)
        lines = [f"part {index}: {line}" if several and part is None else line for line in mapped["unmapped"]]
        if strict and lines:
            raise NotCarriedOver(lines)
        written, details = _write(written, mapped, index if several else None, strict)
        unmapped += lines + mapped.get("refused", [])
        reports.append(details)
        presentation = presentation or mapped["presentation"]
        if strict and details["differences"]:
            raise NotCarriedOver([f"read back differently: {d}" for d in details["differences"]])
    details = reports[0] if len(reports) == 1 else {
        **{key: [x for r in reports for x in r[key]]
           for key in ("differences", "read_findings", "writer_findings", "output_findings")},
        "part": None, "parts": reports}
    return (written, {"unmapped": unmapped, "quiddity": details, "presentation": presentation}) if report else written


def _has_pmi(mapped: dict[str, Any]) -> bool:
    pmi_ = mapped["document"]["pmi"]
    return any(pmi_[k] for k in ("datums", "dimensions", "tolerances", "notes")) or pmi_["material"] is not None


def _write(geometry: bytes, mapped: dict[str, Any], which: int | None, strict: bool):
    """haecceity writing one part's PMI onto ``geometry``. Items to_xcaf kept whole that its
    writer refuses are left out, and said so (in ``mapped["refused"]``): those it names, then the
    kept attributes (which may restate a kept thread), then all that was kept."""
    mapped.setdefault("refused", [])
    for attempt in range(4):
        try:
            return pmi.write(geometry, mapped["document"], report=True, part=which)
        except pmi.PmiError as error:
            refused = _refused(mapped, str(error), attempt)
            if not refused or attempt == 3:
                raise
            mapped["refused"] += refused
            if strict:
                raise NotCarriedOver(refused) from error
