"""XCAF to AP242: the tolerance modifiers and zones XCAF has, area datum targets, the document's
own callouts and saved views, and documents of several parts."""

import json

import pytest
from quiddity import pmi

import files
from make_documents import build_modifiers, build_two_parts
from test_reader import CADGEN
from xcaf_pmi import read, to_haecceity, to_step, to_xcaf
from xcaf_pmi.cli import main
from xcaf_pmi.reader import read_document


@pytest.fixture(scope="module")
def modifiers(tmp_path_factory):
    return build_modifiers(tmp_path_factory.mktemp("modifiers") / "plate.xbf")


@pytest.fixture(scope="module")
def two_parts(tmp_path_factory):
    return build_two_parts(tmp_path_factory.mktemp("two") / "two.xbf")


def _tolerances(step: bytes) -> dict:
    return {t["id"]: t["value"] for t in pmi.read(step)["pmi"]["tolerances"]}


def test_tolerance_modifiers(modifiers):
    written, report = to_step(modifiers, report=True)
    assert report["quiddity"]["differences"] == []
    t = _tolerances(written)
    assert t["free-flat"]["modifiers"] == ["free_state"]
    assert t["tangent-parallel"]["modifiers"] == ["tangent_plane"]
    assert t["statistical-position"]["modifiers"] == ["least_material_requirement", "statistical_tolerance"]
    assert t["statistical-position"]["maximum"]["quantity"]["length"]["value"] == "0.3"
    assert t["each-straight"]["modifiers"] == ["line_element", "common_zone"]
    assert t["angled-runout"]["zone"]["runout_angle"]["quantity"]["angle"]["value"] == "30.0"
    features = {f["id"]: f["value"] for f in pmi.read(written)["pmi"]["features"]}
    assert features[t["around-profile"]["target"]["feature"]]["group"]["kind"] == "all_around_shape_aspect"


def test_projected_zone_is_reported(modifiers):
    # AP242 states where a projected zone ends; XCAF holds only its length.
    _, report = to_step(modifiers, report=True)
    assert report["unmapped"] == ["tolerance projected-position: its projected zone (8.0), whose end XCAF does not hold"]


def test_area_datum_target(modifiers):
    """Datum E's one target is an area, held as the target's shape in XCAF (no reference shapes)."""
    found = read(modifiers)
    e = next(d for d in found["datums"] if d["name"] == "E")
    assert e["faces"] == [] and e["target"]["area"] == [{"part": 0, "face": 2, "name": "top"}]
    written = pmi.read(to_step(modifiers))["pmi"]
    target = next(t["value"] for t in written["datum_targets"] if t["id"] == "datum_target/E1")
    features = {f["id"]: f["value"] for f in written["features"]}
    assert len(features[target["shape"]["area"]]["items"]) == 1
    assert [d["value"]["targets"] for d in written["datums"] if d["value"]["label"] == "E"] == [["datum_target/E1"]]
    assert _tolerances(to_step(modifiers))["on-area"]["datums"][0]["references"][0]["datum"] == "datum/E"


def test_saved_views():
    """cadgen's views (iso, and the section A-A) with the items each shows."""
    _, report = to_step(CADGEN, report=True)
    shown = report["presentation"]
    pmi.validate(shown)
    views = {v["name"]: v for v in shown["views"]}
    assert set(views) == {"iso", "A-A"}
    # iso shows 12 items, of which the general profile tolerance has no callout in the document.
    assert len(views["A-A"]["graphics"]) == 4 and len(views["iso"]["graphics"]) == 11
    assert views["iso"]["direction"] and views["iso"]["up"]


def test_callouts_where_the_document_places_them():
    """A STEP's callouts, through to_xcaf's XCAF presentation, come back as the file's own (source
    file), on their annotation planes."""
    found = read_document(to_xcaf(files.step("nist_ctc_01_asme1_ap242-e1.stp")), "ctc01")
    shown = to_haecceity(found)["presentation"]
    pmi.validate(shown)
    graphics = [g for listed in shown["items"].values() for g in listed]
    assert len(shown["items"]) == 17 and all(g["source"] == "file" for g in graphics)
    assert all(g["polylines"] or g["triangles"] for g in graphics)
    planes = {p["id"] for p in shown["planes"]}
    assert all(g["plane_id"] in planes for g in graphics)


def test_cli_writes_the_presentation(tmp_path):
    out = tmp_path / "part.presentation.json"
    assert main(["to-step", str(CADGEN), "-o", str(tmp_path / "part.step"), "--presentation", str(out)]) == 0
    assert json.loads(out.read_text())["schema"] == "haecceity.presentation/1"


def test_two_parts(two_parts):
    """Each part's GD&T on its own part of the STEP."""
    assert [p["name"] for p in read(two_parts)["parts"]] == ["plate", "pin"]
    written, report = to_step(two_parts, report=True)
    assert report["unmapped"] == [] and report["quiddity"]["differences"] == []
    ids = [{k: [x["id"] for x in pmi.read(written, part=i)["pmi"][k]] for k in ("datums", "dimensions", "tolerances")}
           for i in (0, 1)]
    assert ids == [{"datums": ["datum/A"], "dimensions": ["plate-thickness"], "tolerances": ["plate-flatness"]},
                   {"datums": ["datum/P"], "dimensions": ["pin-diameter"], "tolerances": ["pin-perpendicularity"]}]
    pin = pmi.read(to_step(two_parts, 1), part=1)["pmi"]
    assert [t["id"] for t in pin["tolerances"]] == ["pin-perpendicularity"]
    assert pmi.read(to_step(two_parts, 1), part=0)["pmi"]["tolerances"] == []


def test_two_parts_round_trip(two_parts, tmp_path):
    """The two-part STEP back to XCAF and to STEP again keeps each part's GD&T."""
    step = tmp_path / "two.step"
    step.write_bytes(to_step(two_parts))
    again = to_step(to_xcaf(step))
    assert [[t["id"] for t in pmi.read(again, part=i)["pmi"]["tolerances"]] for i in (0, 1)] == \
           [["plate-flatness"], ["pin-perpendicularity"]]
