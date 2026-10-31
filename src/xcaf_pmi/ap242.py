"""An XCAF document straight to AP242 STEP with semantic PMI: its geometry (``geometry_step``),
its GD&T as ``haecceity.pmi/1`` (``to_haecceity``), and haecceity writing the one onto the other
in process (``quiddity.pmi.write``), which reads the result back before returning it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quiddity import pmi

from xcaf_pmi.haecceity import to_haecceity
from xcaf_pmi.reader import geometry_step, open_document, read_document


class NotCarriedOver(ValueError):
    """``to_step(..., strict=True)`` found GD&T it could not carry over; ``unmapped`` lists it."""

    def __init__(self, unmapped: list[str]):
        super().__init__("not carried over:\n" + "\n".join(f"  {line}" for line in unmapped))
        self.unmapped = unmapped


def to_step(document: str | Path | bytes, part: int = 0, *, strict: bool = False,
            report: bool = False) -> bytes | tuple[bytes, dict[str, Any]]:
    """The document as AP242 STEP bytes, its GD&T as semantic PMI on part ``part``.

    What could not be carried over is never dropped silently: with ``strict`` it raises
    ``NotCarriedOver``, as it does for any difference haecceity finds reading the result back; with ``report`` the result is ``(bytes, {"unmapped": [...], "quiddity":
    {...}})``, quiddity's report holding its read-back ``differences`` and its findings.
    haecceity's refusals raise ``quiddity.PmiError``.
    """
    doc = open_document(document)
    found = read_document(doc, "<bytes>" if isinstance(document, bytes) else str(document))
    mapped = to_haecceity(found, part)
    if strict and mapped["unmapped"]:
        raise NotCarriedOver(mapped["unmapped"])
    # quiddity numbers the STEP's parts itself and needs one named only when there are several.
    written, details = pmi.write(geometry_step(doc), mapped["document"], report=True,
                                 part=part if len(found["parts"]) > 1 else None)
    if strict and details["differences"]:
        raise NotCarriedOver([f"read back differently: {d}" for d in details["differences"]])
    return (written, {"unmapped": mapped["unmapped"], "quiddity": details}) if report else written
