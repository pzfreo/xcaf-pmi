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
from xcaf_pmi.geometry import edges, entities, faces, read_step, read_step_faces
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
    assert lost["method"] == "geometry" and lost["faces"] == list(range(n))
    assert lost["unmatched"] == [] and lost["ambiguous"] == []


FTC10 = "nist_ftc_10_asme1_ap242-e2.stp"


def test_geometry_fallback_is_one_to_one():
    """FTC-10's supplemental surfaces lie on its solid's faces (a point of one is on the other):
    matched by geometry alone, each face is still its own, and no OCCT face is used twice."""
    step = files.step(FTC10)
    doc, _ = read_step_faces(step)
    part, offset = _choose(doc, _parts(step), 0)
    lost = faces(step, part, lambda f: None, offset)
    assert lost["faces"] == list(range(len(part.faces)))
    assert lost["unmatched"] == [] and lost["ambiguous"] == []


def test_geometry_fallback_leaves_a_collision_unanchored(monkeypatch):
    """Two faces whose geometry matches the same one face of OCCT's: neither is anchored, both
    are reported, and the face is not given to either."""
    import quiddity

    step = files.step(FTC10)
    doc, _ = read_step_faces(step)
    part, offset = _choose(doc, _parts(step), 0)
    real = json.loads(quiddity.fingerprints(str(step)))
    real["faces"][264] = {**real["faces"][220], "index": 264}
    monkeypatch.setattr(quiddity, "fingerprints", lambda path: json.dumps(real))
    lost = faces(step, part, lambda f: None, offset)
    assert lost["faces"][220] is None and lost["faces"][264] is None
    assert lost["ambiguous"] == [(220, [220]), (264, [220])]
    assert [j for i, j in enumerate(lost["faces"]) if i not in (220, 264)] == \
           [i for i in range(len(part.faces)) if i not in (220, 264)]


def test_entity_numbers_ignore_strings_and_comments(ctc01, tmp_path):
    """``#n=`` inside a string or a comment is not an instance: the faces' entities still read."""
    text = ctc01.read_bytes().replace(b"DATA;", b"DATA;\n/* #1=NOT_AN_INSTANCE(); */", 1)
    text = text.replace(b"PRODUCT('", b"PRODUCT('#12=X;/*", 1)
    assert b"#12=X;/*" in text
    odd = tmp_path / "odd.stp"
    odd.write_bytes(text)
    doc, entity_of = read_step_faces(odd)
    part, offset = _choose(doc, _parts(odd), 0)
    assert faces(odd, part, entity_of, offset)["method"] == "index"


def _pmi_edges(step):
    """The ``edge_curve`` entities the STEP's PMI is on (its geometric_item_specific_usages)."""
    _, held = entities(step)
    return {refs[-1] for kind, refs in held.values()
            if kind == "GEOMETRIC_ITEM_SPECIFIC_USAGE" and refs and held.get(refs[-1], ("",))[0] == "EDGE_CURVE"}


@pytest.mark.parametrize("name, method, unchecked", [
    (CTC01, "index", []),
    # OCCT makes more edges than the file has (seams, splits): haecceity's numbering is not OCCT's.
    ("nist_ftc_07_asme1_ap242-e2.stp", "entity", []),
    (FTC10, "entity", []),
    # haecceity numbers edges the file has not before these two: they cannot be checked.
    ("nist_stc_10_asme1_ap242-e2.stp", "entity", [194, 293]),
])
def test_edges_are_matched_by_entity(name, method, unchecked):
    step = files.step(name)
    doc, entity_of = read_step_faces(step)
    part, offset = _choose(doc, _parts(step), 0)
    used = [i["edge"] for f in pmi.read(step)["pmi"]["features"] for i in f["value"].get("items", []) if "edge" in i]
    matched = edges(step, part, entity_of, used, faces(step, part, entity_of, offset)["faces"], offset)
    assert matched["method"] == method and [k for k, _ in matched["unmatched"]] == unchecked
    placed = [j for j in matched["edges"].values() if j is not None]
    assert len(placed) == len(set(placed)) == len(set(used)) - len(unchecked)
    assert all(entity_of(part.edges[j][1]) in _pmi_edges(step) for j in placed)


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
    # haecceity refuses these two whole: to_xcaf takes OCCT's own reading.
    'nist_stc_06_asme1_ap242-e3.stp': {
        'dimensions': (0, 0, 19), 'dimension tolerances': (0, 0, 19), 'tolerances': (0, 0, 26),
        'modifiers': (0, 0, 4), 'datums': (6, 6, 6), 'datum systems': (22, 22, 23), 'notes': (0, 0, 0),
        'material': (0, 0, 0), 'density': (0, 0, 0), 'names': (0, 0, 0),
    },
    'nist_stc_09_asme1_ap242-e4.stp': {
        'dimensions': (20, 20, 20), 'dimension tolerances': (19, 19, 20), 'tolerances': (25, 25, 27),
        'modifiers': (10, 10, 11), 'datums': (8, 8, 8), 'datum systems': (26, 26, 26), 'notes': (0, 0, 0),
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
    # haecceity does not read the position tolerance (a runout zone with no angle): OCCT's reading.
    "cadgen plate, OCCT's export": {
        'dimensions': (4, 4, 4), 'dimension tolerances': (4, 4, 4), 'tolerances': (5, 5, 5),
        'modifiers': (0, 0, 0), 'datums': (3, 3, 3), 'datum systems': (4, 4, 4), 'notes': (0, 0, 2),
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
    assert set(table) == set(GAPS)
    for name, row in table.items():
        assert row == GAPS[name], name


# (OCCT's reader right, to_xcaf right, stated), over every category of every file of each source.
TOTALS = {"NIST (expected PMI)": (590, 611, 738),
          "Specify and draftwright (haecceity's own reading)": (171, 224, 232),
          "cadgen (its document)": (44, 55, 66)}


def test_better_than_native(table):
    """On every file, to_xcaf gets every category at least as right as OCCT's reader: where
    haecceity refuses a file or an item, it takes OCCT's reading of it."""
    for name, row in table.items():
        for key, (native, ours, _) in row.items():
            assert ours >= native, (name, key)
    assert gaps.totals(table) == TOTALS


@pytest.mark.parametrize("name", ["nist_stc_06_asme1_ap242-e3.stp", "nist_stc_09_asme1_ap242-e4.stp"])
def test_haecceity_refuses(name):
    """quiddity 0.4.0 refuses these models' attributes ("duplicate or empty item id"), and so the
    whole file: to_xcaf takes OCCT's own reading of the GD&T, and says so."""
    with pytest.raises(PmiError, match="duplicate or empty item id"):
        pmi.read(files.step(name))
    doc, report = to_xcaf(files.step(name), report=True)
    assert [f["detail"] for f in report["findings"] if f["kind"] == "fallback"] == \
           [f"haecceity refuses the part ({_refusal(name)}); OCCT's own reading of its GD&T is used"]
    assert read_document(doc, name)["tolerances"]


def _refusal(name):
    try:
        pmi.read(files.step(name))
    except PmiError as error:
        return str(error)


def test_an_item_haecceity_does_not_read_is_taken_from_occt(tmp_path):
    """OCCT's export of cadgen's plate states its position tolerance's zone as a runout zone with
    no angle, which haecceity does not read: to_xcaf takes that tolerance, with its datums, from
    OCCT's own reading."""
    from test_reader import CADGEN

    step = tmp_path / "occt.step"
    step.write_bytes(gaps.occt_step(CADGEN))
    doc, report = to_xcaf(step, report=True)
    assert [f["detail"] for f in report["findings"] if f["kind"] == "fallback"] == \
           ["tolerance Position 0.1: haecceity did not read it; OCCT's own reading of it is used"]
    position = [t for t in read_document(doc, "occt")["tolerances"] if t["type"] == "Position"]
    assert len(position) == 1 and position[0]["datums"] == ["A", "B", "C"] and position[0]["faces"]


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


# What XCAF cannot hold that the round trip still loses, and why: STC-10 has an attribute on an
# edge whose number haecceity gives cannot be checked against the file's edges (to_xcaf says so).
KEPT_LOST = {"spindle_shaft_fit.step": {}, "nist_stc_10_asme1_ap242-e2.stp": {"attributes": 1}}


@pytest.mark.parametrize("name", KEPT_LOST)
def test_round_trip_keeps_what_xcaf_cannot_hold(name, tmp_path):
    """Threads, knurls, surface texture, general tolerances, tolerance relations and attributes
    have no XCAF GD&T: to_xcaf keeps each on the document, through an .xbf, for to_step, on the
    same faces and edges."""
    step = files.step(name)
    before = gaps.placed(step)
    doc, report = to_xcaf(step, report=True)
    xbf = save(doc, tmp_path / "part.xbf")
    assert read(xbf)["kept"]
    written = tmp_path / "written.step"
    written.write_bytes(to_step(xbf))
    after = gaps.placed(written)
    assert any(before[k] for k in EXTRA)
    lost = {}
    for key in EXTRA:
        left = [json.dumps(x, sort_keys=True) for x in after[key]]
        for x in before[key]:
            text = json.dumps(x, sort_keys=True)
            if text in left:
                left.remove(text)
            else:
                lost[key] = lost.get(key, 0) + 1
        assert left == [], key
    assert lost == KEPT_LOST[name]
    if lost:
        assert any("left unanchored" in line and line.startswith("edge ") for line in report["unmapped"])


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
    for misuse in (["--strict"],  # --strict belongs to to-step
                   ["--part", "-1"], ["--part", "one"]):
        with pytest.raises(SystemExit) as exit:
            main(["to-xcaf", str(ctc01), "-o", str(tmp_path / "part.xbf"), *misuse])
        assert exit.value.code == 2, misuse
    with pytest.raises(SystemExit) as exit:  # the output is an .xbf
        main(["to-xcaf", str(ctc01), "-o", str(tmp_path / "part.step")])
    assert exit.value.code == 2


def test_cli_failures(ctc01, tmp_path, capsys):
    """A part the file has not, or an output folder that does not exist: a clear message and exit
    status 1 (2 is a usage error, 3 --strict's refusal)."""
    xbf = tmp_path / "part.xbf"
    assert main(["to-xcaf", str(ctc01), "-o", str(xbf)]) == 0
    assert main(["to-xcaf", str(ctc01), "-o", str(xbf), "--part", "5"]) == 1
    assert "no part 5" in capsys.readouterr().err
    assert main(["to-xcaf", str(ctc01), "-o", str(tmp_path / "missing" / "part.xbf")]) == 1
    assert "does not exist" in capsys.readouterr().err
    assert main(["to-step", str(xbf), "-o", str(tmp_path / "back.step"), "--part", "5"]) == 1
    assert "no part 5: the document has 1 " in capsys.readouterr().err  # not the empty compound OCCT reads
    assert main(["to-step", str(xbf), "-o", str(tmp_path / "missing" / "back.step")]) == 1
    assert "No such file or directory" in capsys.readouterr().err
    with pytest.raises(SystemExit) as exit:
        main(["to-step", str(xbf), "-o", str(tmp_path / "back.step"), "--part", "-1"])
    assert exit.value.code == 2


def test_findings_are_read_or_said_not_to_be(monkeypatch, tmp_path):
    """haecceity's findings come from quiddity's command line, given an absolute path (a file
    named like an option is still a file); where it fails, a finding says so."""
    import subprocess

    from xcaf_pmi import from_step

    odd = tmp_path / "-part.stp"
    shutil.copy(files.step(CTC01), odd)
    monkeypatch.chdir(tmp_path)
    assert sum("no value is stated" in f["detail"] for f in from_step.findings("-part.stp")) == 4
    monkeypatch.setattr(from_step, "_quiddity", lambda *args: subprocess.CompletedProcess(args, 1, "", "boom"))
    assert from_step.findings(odd) == [{"kind": "warning", "part": None, "entity": None, "ids": [],
                                        "detail": "haecceity's findings could not be read (quiddity pmi read: boom)"}]


def test_findings_of_each_part():
    """A file of several parts: quiddity's ``pmi read`` needs a part named, so each part's."""
    from xcaf_pmi.from_step import findings

    assert not [f for f in findings(files.step("assembly_plate_pin.step"), 2) if f["kind"] == "warning"]


@pytest.mark.parametrize("name", [CTC01, "nist_ctc_02_asme1_ap242-e2.stp"])
def test_occt_writer_keeps_the_datum_systems(name, tmp_path):
    """Each reference to a datum is a datum of its own with its compartment's position, as OCCT's
    reader makes it: OCCT's own STEP writer then keeps every tolerance and its datum system."""
    systems = lambda found: sorted(tuple(dict.fromkeys(t["datums"])) for t in found["tolerances"])
    xbf = save(to_xcaf(files.step(name)), tmp_path / "part.xbf")
    ours = read(xbf)
    assert all(d["position"] for t in ours["tolerances"] for d in t["datum_refs"])
    back = tmp_path / "occt.step"
    back.write_bytes(gaps.occt_step(xbf))
    again = read_document(read_step(back, gdt=True), "occt")
    assert systems(again) == systems(ours) and sum(1 for s in systems(ours) if s) > 0


def _rewrite_kept(xbf, out, change):
    """The document with each fragment to_xcaf kept passed through ``change(entry, text)``, which
    gives the attribute's new text (or None to leave it)."""
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString
    from OCP.TDF import TDF_ChildIterator

    from xcaf_pmi.reader import _entry, open_document
    from xcaf_pmi.xcaf import KEPT

    doc = open_document(xbf)
    held = TDataStd_AsciiString()
    it = TDF_ChildIterator(doc.Main(), True)
    while it.More():
        label = it.Value()
        if label.IsAttribute(KEPT) and label.FindAttribute(KEPT, held):
            text = change(_entry(label), held.Get().ToCString())
            if text is not None:
                TDataStd_AsciiString.Set_s(label, KEPT, TCollection_AsciiString(text))
        it.Next()
    return save(doc, out)


def test_an_item_edited_since_to_xcaf_is_written_as_edited(tmp_path):
    """FTC-07's tolerance 0:1:4:47 is kept whole (XCAF cannot hold its projected zone's end).
    Its value edited in the document, to_step writes the edited value, from XCAF's own reading,
    and says that what was kept for it is left out."""
    from OCP.TDF import TDF_Label, TDF_Tool
    from OCP.TCollection import TCollection_AsciiString
    from OCP.XCAFDoc import XCAFDoc_GeomTolerance

    from xcaf_pmi.reader import open_document

    xbf = save(to_xcaf(files.step("nist_ftc_07_asme1_ap242-e2.stp")), tmp_path / "part.xbf")
    kept = next(k for k in read(xbf)["kept"] if k["items"][0]["group"] == "tolerances")
    id, was = kept["items"][0]["item"]["id"], kept["items"][0]["item"]["value"]["magnitude"]
    doc = open_document(xbf)
    label = TDF_Label()
    TDF_Tool.Label_s(doc.Main().Data(), TCollection_AsciiString(kept["on"]), label)
    attr = XCAFDoc_GeomTolerance.Set_s(label)
    obj = attr.GetObject()
    edited = obj.GetValue() + 0.1
    obj.SetValue(edited)
    attr.SetObject(obj)
    written, report = to_step(save(doc, tmp_path / "edited.xbf"), report=True)
    tolerance = next(t["value"] for t in pmi.read(written, part=0)["pmi"]["tolerances"] if t["id"] == id)
    assert float(tolerance["magnitude"]["quantity"]["length"]["value"]) == pytest.approx(edited) != float(
        was["quantity"]["length"]["value"])
    assert f"tolerances {id}: edited in the document since to_xcaf" in "\n".join(report["unmapped"])
    # Unedited, what was kept is restored, and nothing is said of it.
    _, plain = to_step(xbf, report=True)
    assert not any(id in line for line in plain["unmapped"])


def test_kept_items_on_faces_that_changed_are_left_out(tmp_path):
    """What is kept on the part refers to faces by OCCT's index: an item whose face is no longer
    the one it was kept on (its fingerprint differs) is left out, and said so."""
    step = files.step("spindle_shaft_fit.step")
    xbf = save(to_xcaf(step), tmp_path / "part.xbf")
    part = next(k for k in read(xbf)["kept"] if k["on"] == k["part"])
    face = next(iter(part["fingerprints"]["faces"]))

    def moved(entry, text):
        fragment = json.loads(text)
        if entry != part["on"]:
            return None
        fragment["fingerprints"]["faces"][face]["area"] += 1.0
        return json.dumps(fragment)

    _, report = to_step(_rewrite_kept(xbf, tmp_path / "moved.xbf", moved), report=True)
    gone = [line for line in report["unmapped"] if "are not those to_xcaf kept it on" in line]
    _, plain = to_step(xbf, report=True)
    assert gone and not any("are not those to_xcaf kept it on" in line for line in plain["unmapped"])


@pytest.mark.parametrize("change, said", [
    (lambda fragment: {**fragment, "schema": "xcaf-pmi.kept/99"}, "its schema 'xcaf-pmi.kept/99' is not"),
    (lambda fragment: {**fragment, "part": "0:1:1:99"}, "for part 0:1:1:99, which the document does not have"),
    (lambda fragment: "{not json", "not readable"),
    (lambda fragment: {k: v for k, v in fragment.items() if k != "state"}, "without the state to check it against"),
])
def test_kept_fragments_that_cannot_be_used_are_reported(change, said, tmp_path):
    xbf = save(to_xcaf(files.step("spindle_shaft_fit.step")), tmp_path / "part.xbf")
    changed = lambda entry, text: (lambda out: out if isinstance(out, str) else json.dumps(out))(change(json.loads(text)))
    _, report = to_step(_rewrite_kept(xbf, tmp_path / "changed.xbf", changed), report=True)
    assert any(said in line for line in report["unmapped"]), report["unmapped"]


def test_an_item_kept_twice_is_written_once(tmp_path):
    """Two fragments holding one id (to_xcaf renames datums as to_haecceity names them): the
    second is left out, and said so, rather than written twice (which haecceity refuses)."""
    xbf = save(to_xcaf(files.step("nist_ftc_07_asme1_ap242-e2.stp")), tmp_path / "part.xbf")
    found = read(xbf)
    tolerance = next(k for k in found["kept"] if k["items"][0]["group"] == "tolerances")
    part = next(k for k in found["kept"] if k["on"] == k["part"])

    def doubled(entry, text):
        if entry != part["on"]:
            return None
        fragment = json.loads(text)
        fragment["items"] += tolerance["items"]
        fragment["features"] += [f for f in tolerance["features"] if f not in fragment["features"]]
        return json.dumps(fragment)

    written, report = to_step(_rewrite_kept(xbf, tmp_path / "doubled.xbf", doubled), report=True)
    id = tolerance["items"][0]["item"]["id"]
    assert [t["id"] for t in pmi.read(written, part=0)["pmi"]["tolerances"]].count(id) == 1
    assert f"tolerances {id}: kept twice by to_xcaf; the second left out" in report["unmapped"]


def test_a_wrong_cached_step_is_written_again(monkeypatch, tmp_path):
    """The decompressed copy in the cache is checked against the verified archive."""
    monkeypatch.setenv("XCAF_PMI_CACHE", str(tmp_path))
    good = files.step(CTC01).read_bytes()
    (tmp_path / "steps" / CTC01).write_bytes(b"ISO-10303-21; truncated")
    assert files.step(CTC01).read_bytes() == good


@pytest.mark.parametrize("required, outcome", [(None, "Skipped"), ("1", "Failed")])
def test_a_test_file_not_fetched(required, outcome, monkeypatch, tmp_path):
    """Offline, a test needing a fetched file is skipped, or fails where every file is required
    (CI sets XCAF_PMI_REQUIRE_FIXTURES=1)."""
    import urllib.request

    monkeypatch.setenv("XCAF_PMI_CACHE", str(tmp_path))
    if required:
        monkeypatch.setenv("XCAF_PMI_REQUIRE_FIXTURES", required)
    else:
        monkeypatch.delenv("XCAF_PMI_REQUIRE_FIXTURES", raising=False)

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    with pytest.raises(BaseException) as raised:
        files.step(FTC10)
    assert type(raised.value).__name__ == outcome


def test_a_reference_to_a_datum_of_targets_is_each_target():
    """A datum defined by its targets alone (CTC-02's A, B and C): a tolerance's reference to it
    is a datum for each target, as OCCT's own reader makes it."""
    step = files.step("nist_ctc_02_asme1_ap242-e2.stp")
    refs = lambda found: sorted(tuple(r["name"] for r in t["datum_refs"]) for t in found["tolerances"])
    ours = refs(read_document(to_xcaf(step), "ours"))
    assert ours == refs(read_document(read_step(step, gdt=True), "native"))
    assert ("A", "A", "A", "B", "B", "B", "B", "C") in ours


def test_a_tolerance_xcaf_cannot_hold_is_reported(ctc01):
    """XCAF holds a ± tolerance only on a dimension with a value: one without is reported."""
    from xcaf_pmi import xcaf

    semantic = pmi.read(ctc01)
    d = next(x for x in semantic["pmi"]["dimensions"]
             if isinstance(x["value"]["tolerance"], dict) and "deviations" in x["value"]["tolerance"])
    d["value"]["nominal"] = None
    doc, _ = read_step_faces(ctc01)
    part, _ = _choose(doc, _parts(ctc01), 0)
    built = xcaf.build(doc, part, semantic, list(range(len(part.faces))))
    assert f"dimension {d['id']}: its ± tolerance, which XCAF holds only on a dimension with a value" in built["unmapped"]
