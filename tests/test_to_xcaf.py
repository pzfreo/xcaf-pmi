"""AP242 STEP to XCAF (``to_xcaf``): face numbering, what it carries against OCCT's own reader
(the gap table), and the round trip back through ``to_step``."""

import json
import random
import shutil

import pytest
from quiddity import PmiError, pmi

import files
import gaps
from xcaf_pmi import read, save, to_step, to_xcaf
from xcaf_pmi.cli import main
from xcaf_pmi.from_step import _choose, _parts
from xcaf_pmi.geometry import faces, read_step_faces
from xcaf_pmi.reader import read_document

CTC01 = "nist_ctc_01_asme1_ap242-e1.stp"
EVERY = files.NIST + files.SPECIFY + files.DRAFTWRIGHT_FILES
# Groups haecceity.pmi/1 has and XCAF's GD&T has not: kept on the document for to_step.
EXTRA = ["general", "threads", "knurls", "holes", "surface_textures", "tolerance_relations", "attributes", "standards"]


@pytest.fixture(scope="module")
def ctc01():
    return files.step(CTC01)


def test_ctc01(ctc01):
    doc, report = to_xcaf(ctc01, report=True)
    assert report["faces"] == ["index"]
    assert report["added"] == {"datum": 3, "dimension": 12, "tolerance": 6, "attribute": 5}
    found = read_document(doc, "ctc01")
    assert sorted({d["name"] for d in found["datums"]}) == ["A", "B", "C"]
    position = [t for t in found["tolerances"] if t["type"] == "Position"]
    assert [t["value"] for t in position] == [0.75, 0.75] and position[0]["datums"] == ["A", "B", "C"]
    assert sorted(t["value"] for t in found["tolerances"]) == [0.2, 0.5, 0.75, 0.75, 1.25, 1.5]
    profile = next(t for t in found["tolerances"] if t["value"] == 0.5)
    assert profile["modifiers"] == ["XCAFDimTolObjects_GeomToleranceModif_All_Around"]
    ranged = [d["range"] for d in found["dimensions"] if "range" in d]
    assert ranged == [{"lower": 34.8, "upper": 35.2}] * 2
    # haecceity's findings pass through: four dimensions state no value.
    assert sum("no value is stated" in f["detail"] for f in report["findings"]) == 4


def test_takes_bytes(ctc01):
    found = read_document(to_xcaf(ctc01.read_bytes()), "bytes")
    assert len(found["tolerances"]) == 6


@pytest.mark.parametrize("name", EVERY)
def test_face_numbering(name):
    """haecceity numbers a part's faces in the order OCCT's reader makes them: each face is the
    STEP entity haecceity says it is (quiddity.evidence)."""
    step = files.step(name)
    doc, entity_of = read_step_faces(step)
    theirs = _parts(step)
    for i in range(len(theirs)):
        part, offset = _choose(doc, theirs, i)
        assert faces(step, part, entity_of, offset)["method"] == "index"


def test_face_numbering_falls_back(ctc01):
    doc, entity_of = read_step_faces(ctc01)
    part, offset = _choose(doc, _parts(ctc01), 0)
    n = len(part.faces)
    # Faces OCCT made in another order are matched by their entity …
    order = list(range(n))
    random.Random(5).shuffle(order)
    own = [face for _, face, _ in part.faces]
    moved = faces(ctc01, part, lambda f: entity_of(own[order[own.index(f)]]) if f in own else None, offset)
    assert moved["method"] == "entity" and moved["faces"] == [order.index(i) for i in range(n)]
    # … and faces of no entity known, by their geometry.
    lost = faces(ctc01, part, lambda f: None, offset)
    assert lost["method"] == "geometry" and lost["faces"] == list(range(n)) and lost["unmatched"] == []


# What OCCT's reader and to_xcaf get right of what each file states, per category:
# (OCCT right, to_xcaf right, stated). tests/gaps.py says how it is counted; ``python
# tests/gaps.py`` prints it.
GAPS = {
    'nist_ctc_01_asme1_ap242-e1.stp': {
        'dimensions': (8, 8, 8), 'dimension tolerances': (8, 8, 8), 'tolerances': (6, 6, 6),
        'modifiers': (1, 1, 1), 'datums': (3, 3, 3), 'datum systems': (5, 5, 5), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_ctc_02_asme1_ap242-e2.stp': {
        'dimensions': (7, 7, 7), 'dimension tolerances': (7, 7, 7), 'tolerances': (22, 22, 22),
        'modifiers': (10, 10, 10), 'datums': (10, 10, 10), 'datum systems': (20, 20, 20), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_ftc_07_asme1_ap242-e2.stp': {
        'dimensions': (17, 17, 17), 'dimension tolerances': (16, 17, 17), 'tolerances': (22, 24, 25),
        'modifiers': (7, 7, 10), 'datums': (5, 5, 5), 'datum systems': (23, 23, 23), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_ftc_10_asme1_ap242-e2.stp': {
        'dimensions': (23, 26, 37), 'dimension tolerances': (23, 26, 37), 'tolerances': (33, 37, 40),
        'modifiers': (5, 8, 10), 'datums': (11, 11, 11), 'datum systems': (31, 35, 36), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_stc_06_asme1_ap242-e3.stp': {
        'dimensions': (0, 0, 19), 'dimension tolerances': (0, 0, 19), 'tolerances': (0, 0, 26),
        'modifiers': (0, 0, 4), 'datums': (6, 0, 6), 'datum systems': (22, 0, 23), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_stc_09_asme1_ap242-e4.stp': {
        'dimensions': (20, 0, 20), 'dimension tolerances': (19, 0, 20), 'tolerances': (25, 0, 27),
        'modifiers': (10, 0, 11), 'datums': (8, 0, 8), 'datum systems': (26, 0, 26), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_stc_10_asme1_ap242-e2.stp': {
        'dimensions': (24, 24, 33), 'dimension tolerances': (23, 23, 33), 'tolerances': (35, 36, 37),
        'modifiers': (8, 8, 9), 'datums': (9, 9, 9), 'datum systems': (32, 32, 33), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'spool_fits.step': {
        'dimensions': (2, 5, 5), 'dimension tolerances': (2, 5, 5), 'tolerances': (5, 5, 5),
        'modifiers': (1, 1, 1), 'datums': (2, 2, 2), 'datum systems': (4, 4, 4), 'notes': (0, 3, 3),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'thumbwheel_thread_knurl.step': {
        'dimensions': (0, 1, 1), 'dimension tolerances': (0, 1, 1), 'tolerances': (2, 2, 2),
        'modifiers': (0, 0, 0), 'datums': (2, 2, 2), 'datum systems': (2, 2, 2), 'notes': (0, 6, 6),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'bolt_thread_knurl.step': {
        'dimensions': (1, 1, 1), 'dimension tolerances': (1, 1, 1), 'tolerances': (1, 1, 1),
        'modifiers': (0, 0, 0), 'datums': (2, 2, 2), 'datum systems': (1, 1, 1), 'notes': (0, 5, 5),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'bracket_positions.step': {
        'dimensions': (14, 14, 14), 'dimension tolerances': (14, 14, 14), 'tolerances': (5, 5, 5),
        'modifiers': (2, 2, 2), 'datums': (3, 3, 3), 'datum systems': (4, 4, 4), 'notes': (0, 3, 3),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'string_post_tapped.step': {
        'dimensions': (3, 3, 3), 'dimension tolerances': (3, 3, 3), 'tolerances': (3, 3, 3),
        'modifiers': (1, 1, 1), 'datums': (1, 1, 1), 'datum systems': (2, 2, 2), 'notes': (0, 4, 4),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_ctc_01_merge.step': {
        'dimensions': (8, 8, 12), 'dimension tolerances': (8, 8, 12), 'tolerances': (7, 7, 7),
        'modifiers': (1, 1, 1), 'datums': (3, 3, 3), 'datum systems': (6, 6, 6), 'notes': (0, 3, 3),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'assembly_plate_pin.step': {
        'dimensions': (15, 16, 16), 'dimension tolerances': (15, 16, 16), 'tolerances': (5, 5, 5),
        'modifiers': (1, 1, 1), 'datums': (5, 5, 5), 'datum systems': (4, 4, 4), 'notes': (0, 8, 8),
        'material': (0, 2, 2), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'spindle_shaft_fit.step': {
        'dimensions': (2, 3, 3), 'dimension tolerances': (2, 3, 3), 'tolerances': (2, 2, 2),
        'modifiers': (0, 0, 0), 'datums': (2, 2, 2), 'datum systems': (2, 2, 2), 'notes': (0, 0, 0),
        'material': (0, 1, 1), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    "cadgen plate, OCCT's export": {
        'dimensions': (4, 4, 4), 'dimension tolerances': (4, 4, 4), 'tolerances': (5, 4, 5),
        'modifiers': (0, 0, 0), 'datums': (3, 3, 3), 'datum systems': (4, 3, 4), 'notes': (0, 0, 2),
        'material': (1, 1, 1), 'density': (1, 1, 1), 'names': (0, 0, 9),
    },
    'cadgen plate, to_step': {
        'dimensions': (4, 4, 4), 'dimension tolerances': (4, 4, 4), 'tolerances': (5, 5, 5),
        'modifiers': (0, 0, 0), 'datums': (3, 3, 3), 'datum systems': (4, 4, 4), 'notes': (0, 2, 2),
        'material': (1, 1, 1), 'density': (1, 1, 1), 'names': (0, 9, 9),
    },
}


@pytest.fixture(scope="module")
def table(tmp_path_factory):
    return gaps.table(tmp_path_factory.mktemp("gaps"))


def test_gap_table(table):
    for name, row in table.items():
        assert row == GAPS[name], name


def test_better_than_native(table):
    """Where haecceity reads the file, to_xcaf gets every category at least as right as OCCT's
    reader, but on OCCT's own export of cadgen's plate, whose position tolerance haecceity
    refuses (a runout zone with no angle; its finding says so)."""
    refused = {"nist_stc_06_asme1_ap242-e3.stp", "nist_stc_09_asme1_ap242-e4.stp", "cadgen plate, OCCT's export"}
    totals = [0, 0]
    for name, row in table.items():
        if name in refused:
            continue
        for key, (native, ours, _) in row.items():
            assert ours >= native, (name, key)
            totals = [totals[0] + native, totals[1] + ours]
    assert totals[1] > totals[0]


@pytest.mark.parametrize("name", ["nist_stc_06_asme1_ap242-e3.stp", "nist_stc_09_asme1_ap242-e4.stp"])
def test_haecceity_refuses(name):
    # quiddity 0.4.0 refuses these models' attributes ("duplicate or empty item id"), and so all.
    with pytest.raises(PmiError, match="duplicate or empty item id"):
        to_xcaf(files.step(name))


# What the round trip loses, by category, and why: haecceity's writer refuses a dimension with
# no value; XCAF does not hold where a projected zone ends, which AP242 requires.
ROUND_TRIP = {
    CTC01: {"dimensions": 4, "dimension tolerances": 4},
    "nist_ftc_07_asme1_ap242-e2.stp": {"modifiers": 4},
    "nist_stc_10_asme1_ap242-e2.stp": {},
    "spool_fits.step": {},
    "bracket_positions.step": {},
    "spindle_shaft_fit.step": {},
}


@pytest.mark.parametrize("name", ROUND_TRIP)
def test_round_trip(name, tmp_path):
    """to_step(to_xcaf(step)) keeps the PMI: haecceity reads back what it wrote (no
    differences), and what it reads is what the STEP stated, but for the losses listed."""
    step = files.step(name)
    before = pmi.read(step)
    xbf = save(to_xcaf(step), tmp_path / "part.xbf")
    written, report = to_step(xbf, report=True)
    assert report["quiddity"]["differences"] == []
    after = pmi.read(written, part=report["quiddity"]["part"] if len(_parts_of(written, tmp_path)) > 1 else None)
    stated, read_back = gaps.haecceity_facts(before), gaps.haecceity_facts(after)
    lost = {key: len(gaps.missed(stated, read_back, key)) for key, _ in gaps.CATEGORIES}
    assert {k: n for k, n in lost.items() if n} == ROUND_TRIP[name]


def _parts_of(written: bytes, tmp_path):
    held = tmp_path / "written.step"
    held.write_bytes(written)
    return _parts(held)


@pytest.mark.parametrize("name", ["spindle_shaft_fit.step", "nist_stc_10_asme1_ap242-e2.stp"])
def test_round_trip_keeps_what_xcaf_cannot_hold(name, tmp_path):
    """Threads, knurls, surface texture, general tolerances, tolerance relations and attributes
    have no XCAF GD&T: to_xcaf keeps each on the document, through an .xbf, for to_step."""
    step = files.step(name)
    before = _units_named(pmi.read(step))
    xbf = save(to_xcaf(step), tmp_path / "part.xbf")
    assert read(xbf)["kept"]
    after = _units_named(pmi.read(to_step(xbf)))
    assert any(before[k] for k in EXTRA)
    for key in EXTRA:
        assert sorted(json.dumps(x.get("value", x), sort_keys=True) for x in after[key]) == \
               sorted(json.dumps(x.get("value", x), sort_keys=True) for x in before[key]), key


def _units_named(document):
    """The PMI with each unit's id replaced by its definition (the ids differ, the units not)."""
    names = {u["id"]: json.dumps(u["value"]) for listed in document["units"].values() for u in listed}
    text = json.dumps(document["pmi"])
    for id, value in names.items():
        text = text.replace(json.dumps(id), json.dumps(value))
    return json.loads(text)


def test_cli_verbs(ctc01, tmp_path, capsys):
    xbf = tmp_path / "part.xbf"
    assert main(["to-xcaf", str(ctc01), "-o", str(xbf)]) == 0
    assert "read finding:" in capsys.readouterr().err
    assert main(["to-step", str(xbf), "-o", str(tmp_path / "back.step")]) == 0
    assert len(pmi.read(tmp_path / "back.step")["pmi"]["tolerances"]) == 6


def test_cli_takes_the_direction_from_the_extension(ctc01, tmp_path, capsys):
    upper = tmp_path / "PART.STP"
    shutil.copy(ctc01, upper)
    assert main([str(upper), "-o", str(tmp_path / "part.xbf")]) == 0
    assert main(["-o", str(tmp_path / "back.step"), str(tmp_path / "part.xbf")]) == 0
    assert (tmp_path / "back.step").read_bytes().startswith(b"ISO-10303-21;")
    capsys.readouterr()
    assert main([str(tmp_path / "part.igs"), "-o", str(tmp_path / "x")]) == 2
    err = capsys.readouterr().err
    assert "xcaf-pmi to-step" in err and "xcaf-pmi to-xcaf" in err


def test_cli_to_xcaf_flags(ctc01, tmp_path):
    with pytest.raises(SystemExit):  # --strict belongs to to-step
        main(["to-xcaf", str(ctc01), "-o", str(tmp_path / "part.xbf"), "--strict"])
    with pytest.raises(SystemExit):  # the output is an .xbf
        main(["to-xcaf", str(ctc01), "-o", str(tmp_path / "part.step")])
