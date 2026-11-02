"""A general tolerance: XCAF has none, so code-first CAD (cadgen) states "ISO 2768-m" as a note on
the part. ``to_haecceity`` writes a note whose whole text states one as the part's general
tolerance, and ``to_xcaf`` writes a STEP's general tolerance as such a note (kept whole on it)."""

from pathlib import Path

import pytest
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_NoteComment
from quiddity import pmi

import files
from xcaf_pmi import read, save, to_haecceity, to_step, to_xcaf
from xcaf_pmi.haecceity import general_tolerance
from xcaf_pmi.reader import open_document

CADGEN = Path(__file__).parent / "fixtures" / "cadgen_pmi_plate.xbf"


@pytest.mark.parametrize("text, linear, geometric", [
    ("ISO 2768-m", "m", None),
    ("ISO 2768-mK", "m", "K"),
    ("ISO 2768-1 m", "m", None),
    ("iso 2768-mk", "m", "K"),
    ("ISO2768 - f", "f", None),
    ("ISO 2768 cL", "c", "L"),
    ("GENERAL TOLERANCES ISO 2768-m", "m", None),
    ("General tolerances: ISO 2768-vH", "v", "H"),
    ("Tolerances per ISO 2768-f", "f", None),
    ("TOLERANCES PER ISO 2768-mK.", "m", "K"),
    ("  general   tolerances\n ISO 2768-m ", "m", None),
])
def test_recognised_wordings(text, linear, geometric):
    assert general_tolerance(text) == ({"linear": linear, "geometric": geometric}, None)


@pytest.mark.parametrize("text, why", [
    ("ISO 2768-m unless otherwise stated", "states more than the general tolerance"),
    ("DIN ISO 2768-mK", "states more than the general tolerance"),
    ("Remove burrs. ISO 2768-m", "states more than the general tolerance"),
    ("ISO 2768-x", "states no ISO 2768 class"),
    ("ISO 2768-1 mK", "ISO 2768-1 has no geometric class"),
    ("ISO 22081", "names ISO 22081"),
    ("General specifications ISO 22081", "names ISO 22081"),
    ("GENERAL TOLERANCES DIN 7168-m", "names no standard haecceity has a general tolerance for"),
])
def test_what_stays_text(text, why):
    standard, reason = general_tolerance(text)
    assert standard is None and why in reason


def test_other_notes_are_not_general_tolerances():
    assert general_tolerance("Remove all burrs and break sharp edges") == (None, None)


def _cadgen_with(tmp_path, *notes):
    """cadgen's plate with more notes, each attached as cadgen attaches a note of the part: on the
    part's own label (``notes`` are (text, name) pairs, or (text, name, "face") for one on a face)."""
    from OCP.collections import Sequence_TDF_Label

    doc = open_document(CADGEN)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    seq = Sequence_TDF_Label()
    shapes.GetShapes(seq)
    part = next(seq.Value(i) for i in range(1, seq.Length() + 1) if not shapes.IsAssembly_s(seq.Value(i)))
    tool = XCAFDoc_DocumentTool.NotesTool_s(doc.Main())
    for text, name, *on in notes:
        label = tool.CreateComment(TCollection_ExtendedString("cadgen"), TCollection_ExtendedString(""),
                                   TCollection_ExtendedString(text, True)).Label()
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name, True))
        if on:
            tool.AddNoteToSubshape(label, part, 1)
        else:
            tool.AddNote(label, part)
    tmp_path.mkdir(parents=True, exist_ok=True)
    return save(doc, tmp_path / "plate.xbf")


def test_a_cadgen_note_is_written_as_the_general_tolerance(tmp_path):
    xbf = _cadgen_with(tmp_path, ("GENERAL TOLERANCES ISO 2768-mK", "general-tolerance"))
    mapped = to_haecceity(read(xbf))
    general = mapped["document"]["pmi"]["general"]
    assert general == [{"id": "general-tolerance", "value": {"class": {
        "text": "ISO 2768-mK", "standard": {"linear": "m", "geometric": "K"}}}}]
    # Not written twice: cadgen's own two notes are the only notes.
    assert [n["value"]["text"] for n in mapped["document"]["pmi"]["notes"]] == [
        "Remove all burrs and break sharp edges", "Mask these features before coating with primer"]
    assert mapped["findings"] == ["note general-tolerance ('GENERAL TOLERANCES ISO 2768-mK') "
                                  "written as general tolerance ISO 2768-mK"]

    written, report = to_step(xbf, report=True)
    assert report["findings"] == mapped["findings"]
    assert report["quiddity"]["differences"] == []
    # Only cadgen's own note on two things: the general tolerance is carried.
    assert report["unmapped"] == ["note 0:1:9:1:2: also on dimension hole-diameter "
                                  "(a note has one owner, here feature feature/15)"]
    back = pmi.read(written)["pmi"]
    assert [g["value"] for g in back["general"]] == [general[0]["value"]]
    assert "ISO 2768-mK" not in [n["value"]["text"] for n in back["notes"]]


def test_notes_that_stay_text(tmp_path):
    """A note saying more than the tolerance, an unsupported standard, one on a face, and two
    general tolerances on one part: each stays text, and the findings say why."""
    xbf = _cadgen_with(tmp_path, ("ISO 2768-m unless otherwise stated", "more"), ("ISO 22081", "specification"),
                       ("ISO 2768-f", "on-face", "face"))
    mapped = to_haecceity(read(xbf))
    texts = [n["value"]["text"] for n in mapped["document"]["pmi"]["notes"]]
    assert texts[2:] == ["ISO 2768-m unless otherwise stated", "ISO 22081", "ISO 2768-f"]
    assert mapped["document"]["pmi"]["general"] == []
    assert mapped["findings"] == [
        "note more ('ISO 2768-m unless otherwise stated') kept as text: it states more than the general tolerance",
        "note specification ('ISO 22081') kept as text: it names ISO 22081, which haecceity has no general "
        "tolerance for (only ISO 2768)",
        "note on-face ('ISO 2768-f') kept as text: it is on more than the part, and a general tolerance is of "
        "the whole part"]

    two = to_haecceity(read(_cadgen_with(tmp_path / "two", ("ISO 2768-m", "first"), ("ISO 2768-f", "second"))))
    assert two["document"]["pmi"]["general"] == []
    assert [n["value"]["text"] for n in two["document"]["pmi"]["notes"]][2:] == ["ISO 2768-m", "ISO 2768-f"]
    assert all("the part's notes state 2 general tolerances" in line for line in two["findings"])
    assert len(two["findings"]) == 2


# A STEP's general tolerance: draftwright's spindle states it alone; Specify's spool states it as a
# note of the part ('general tolerances', "ISO 2768-m") too, which XCAF holds as that note.
ROUND_TRIPS = {"spindle_shaft_fit.step": ["general"], "spool_fits.step": ["notes", "general"]}


def _through_xcaf(name, tmp_path):
    step = files.step(name)
    doc, report = to_xcaf(step, report=True)
    return step, save(doc, tmp_path / "part.xbf"), report


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_a_step_general_tolerance_becomes_a_note_and_round_trips(name, tmp_path):
    step, xbf, report = _through_xcaf(name, tmp_path)
    before = pmi.read(step)["pmi"]
    assert [g["value"]["class"]["text"] for g in before["general"]] == ["ISO 2768-m"]
    assert report["added"]["general tolerance"] == 1
    assert not any(line.startswith("general tolerance") for line in report["unmapped"])
    # One XCAF note on the part in the canonical wording (the STEP's own, or one named by the
    # tolerance's id), with what XCAF cannot hold of it kept whole on it.
    found = read(xbf)
    [note] = [n for n in found["notes"] if n["text"] == "ISO 2768-m"]
    assert note["on"] == [{"part": 0}]
    if ROUND_TRIPS[name] == ["general"]:
        assert note["name"] == before["general"][0]["id"]
    assert [[i["group"] for i in k["items"]] for k in found["kept"] if k["on"] == note["id"]] == [ROUND_TRIPS[name]]

    written, back_report = to_step(xbf, report=True)
    assert back_report["quiddity"]["differences"] == []
    back = pmi.read(written)["pmi"]
    assert back["general"] == before["general"]
    assert [(n["id"], n["value"]) for n in back["notes"]] == [(n["id"], n["value"]) for n in before["notes"]]
    # The note read as the general tolerance, unless it was the STEP's own note, restored as such.
    assert back_report["findings"] == ([] if "notes" in ROUND_TRIPS[name] else
                                       [f"note {note['name']} ('ISO 2768-m') written as general tolerance ISO 2768-m"])


@pytest.mark.parametrize("name", ROUND_TRIPS)
def test_a_general_tolerance_note_edited_since_to_xcaf_is_written_as_edited(name, tmp_path):
    from OCP.TDF import TDF_Label, TDF_Tool

    _, xbf, _ = _through_xcaf(name, tmp_path)
    doc = open_document(xbf)
    entry = next(n["id"] for n in read(xbf)["notes"] if n["text"] == "ISO 2768-m")
    label = TDF_Label()
    TDF_Tool.Label_s(doc.GetData(), entry, label)
    XCAFDoc_NoteComment.Get_s(label).Set(TCollection_ExtendedString("ISO 2768-fH"))
    edited = save(doc, tmp_path / "edited.xbf")
    written, report = to_step(edited, report=True)
    back = pmi.read(written)["pmi"]
    assert [g["value"] for g in back["general"]] == [
        {"class": {"text": "ISO 2768-fH", "standard": {"linear": "f", "geometric": "H"}}}]
    assert all("ISO 2768" not in n["value"]["text"] for n in back["notes"])
    assert sum("edited in the document since to_xcaf" in line for line in report["unmapped"]) == len(ROUND_TRIPS[name])


def test_a_step_note_stating_a_general_tolerance_stays_a_note(tmp_path):
    """A STEP's note of the part that reads "ISO 2768-mK", without a general tolerance: to_xcaf keeps
    it whole, so to_step writes it back as the note it was, not as a general tolerance."""
    step = files.step("spindle_shaft_fit.step")
    sent = pmi.read(step)
    sent["pmi"]["general"] = []
    sent["pmi"]["notes"].append({"id": "note-general", "value": {"kind": "semantic text", "text": "ISO 2768-mK",
                                                                 "on": None, "callouts": []}})
    noted = tmp_path / "noted.step"
    noted.write_bytes(pmi.write(step, sent))
    xbf = save(to_xcaf(noted), tmp_path / "noted.xbf")
    written, report = to_step(xbf, report=True)
    back = pmi.read(written)["pmi"]
    assert back["general"] == []
    assert [(n["id"], n["value"]["text"]) for n in back["notes"]] == [("note-general", "ISO 2768-mK")]
    assert report["findings"] == []
