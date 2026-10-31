import json
import os
import subprocess
from pathlib import Path
import re

import pytest

from make_plate import build
from xcaf_pmi import export_step, read
from xcaf_pmi.cli import main


@pytest.fixture(scope="module")
def plate(tmp_path_factory):
    return build(tmp_path_factory.mktemp("plate") / "plate.xbf")


def named(refs):
    return [r.get("name") for r in refs]


def test_reads_every_item(plate):
    found = read(plate)
    assert found["unread"] == []
    assert [d["name"] for d in found["datums"]] == ["A", "B", "C", "D", "D"]
    assert [named(d["faces"]) for d in found["datums"]] == [["bottom"], ["front"], ["left"], ["top"], ["top"]]
    dims = {(d["type"], d["value"]): d for d in found["dimensions"]}
    thickness = dims[("Location_LinearDistance", 10.0)]
    assert (named(thickness["faces"]), named(thickness["to"])) == (["bottom"], ["top"])
    assert thickness["tolerance"] == {"upper": 0.2, "lower": -0.2}
    assert dims[("Size_Diameter", 10.0)]["tolerance"] == {"upper": 0.015, "lower": 0.0}
    assert dims[("Size_Diameter", 10.0)]["fit"] == {"hole": True, "letter": "H", "grade": "IT7"}
    assert "fit" not in thickness
    assert named(dims[("Location_LinearDistance", 30.0)]["to"]) == ["hole"]
    tols = {t["type"]: t for t in found["tolerances"]}
    assert tols["Flatness"]["value"] == 0.05 and named(tols["Flatness"]["faces"]) == ["top"]
    assert tols["Position"]["zone"] == "Diameter"
    assert tols["Position"]["datums"] == ["A", "B", "C"]


def test_reads_datum_targets(plate):
    targets = [d["target"] for d in read(plate)["datums"]]
    assert targets[:3] == [None] * 3
    assert targets[3] == {"type": "Point", "number": 1, "length": 0.0, "width": 0.0, "origin": [-30.0, 0.0, 10.0],
                          "axis": [0.0, 0.0, 1.0], "x": [1.0, 0.0, 0.0]}
    assert (targets[4]["type"], targets[4]["number"], targets[4]["length"], targets[4]["width"]) == ("Rectangle", 2, 8.0, 4.0)


def test_reads_what_each_note_is_on(plate):
    found = read(plate)
    flatness = next(t["id"] for t in found["tolerances"] if t["type"] == "Flatness")
    on = {n["name"]: n["on"] for n in found["notes"]}
    assert [named(item["faces"]) for item in on["unpainted"]] == [["top"]]
    assert on["inspect"] == [{"tolerance": flatness}]
    assert on["edges"] == [{"part": 0}]


def test_plate_as_haecceity_json(plate):
    from xcaf_pmi import to_haecceity

    found = read(plate)
    mapped = to_haecceity(found)
    pmi = mapped["document"]["pmi"]
    assert mapped["unmapped"] == []
    # Unnamed GD&T (OCCT names it all "DGT:Dimension" / "DGT:Tolerance") keeps its entry as its id.
    assert [d["id"] for d in pmi["dimensions"]] == [d["id"] for d in found["dimensions"]]
    hole = next(d for d in pmi["dimensions"] if d["value"]["kind"].get("size", {}).get("kind") == "diameter")
    fit = hole["value"]["tolerance"]["fit"]
    assert fit["class"] == {"deviation": {"letter": "h", "of": "hole"}, "grade": "7"}
    assert [fit["limits"][k]["quantity"]["length"]["value"] for k in ("lower", "upper")] == ["10.0", "10.015"]
    assert pmi["datums"][3]["value"] == {"feature": None, "label": "D", "targets": ["datum_target/D1", "datum_target/D2"]}
    point, rectangle = (t["value"] for t in pmi["datum_targets"])
    assert point["shape"] == "point" and point["number"] == 1
    assert [v["value"] for v in point["placement"]["origin"]] == ["-30.0", "0.0", "10.0"]
    assert rectangle["shape"] == {"rectangle": {"length": {"unit": "unit/mm", "value": "8.0"},
                                                "width": {"unit": "unit/mm", "value": "4.0"}}}
    features = {f["id"]: f["value"]["items"] for f in pmi["features"]}
    assert features[point["on"]] == [{"face": {"name": "top"}}]
    on = {n["id"]: n["value"]["on"] for n in pmi["notes"]}
    assert features[on["unpainted"]["feature"]] == [{"face": {"name": "top"}}]
    assert on["inspect"] == {"tolerance": next(t["id"] for t in found["tolerances"] if t["type"] == "Flatness")}
    assert on["edges"] is None


def test_a_note_on_several_things_keeps_its_faces():
    from xcaf_pmi import to_haecceity

    found = read(CADGEN)
    found["notes"][1]["on"].append({"part": 0})
    mapped = to_haecceity(found)
    assert mapped["unmapped"] == [f"note {found['notes'][1]['id']}: also on dimension hole-diameter, part 0 "
                                  "(a note has one owner, here feature feature/15)"]


def test_faces_carry_names_and_geometry(plate):
    faces = read(plate)["parts"][0]["faces"]
    assert len(faces) == 7
    hole = next(f for f in faces if f.get("name") == "hole")
    assert hole["surface"] == "cylinder"
    top = next(f for f in faces if f.get("name") == "top")
    assert top["centroid"][2] == pytest.approx(10.0)


def test_step_has_no_pmi_and_keeps_face_names_in_face_order(plate, tmp_path):
    step = export_step(plate, tmp_path / "plate.step")
    text = step.read_text(encoding="utf-8")
    assert "AP242_MANAGED_MODEL_BASED_3D_ENGINEERING" in text
    assert not re.search(r"DIMENSIONAL_(SIZE|LOCATION)|GEOMETRIC_TOLERANCE|\bDATUM\(", text)
    # The JSON's face indices are the order of the STEP's faces, the order haecceity numbers them.
    in_step = re.findall(r"ADVANCED_FACE\(\s*'([^']*)'", text)
    in_json = [f.get("name", "") for f in read(plate)["parts"][0]["faces"]]
    assert in_step == in_json


def test_cli(plate, tmp_path, capsys):
    assert main([str(plate), "-o", str(tmp_path / "pmi.json"), "--step", str(tmp_path / "g.step")]) == 0
    assert json.loads((tmp_path / "pmi.json").read_text())["format"] == "xcaf-pmi.intermediate/0"
    assert (tmp_path / "g.step").exists()
    assert main([str(tmp_path / "missing.xbf")]) == 1


def test_refuses_other_files(tmp_path):
    other = tmp_path / "part.step"
    other.write_text("ISO-10303-21;")
    with pytest.raises(ValueError, match="not an XCAF document"):
        read(other)


CADGEN = Path(__file__).parent / "fixtures" / "cadgen_pmi_plate.xbf"


def test_cadgen_plate():
    """text-to-cad's pmi_plate as cadgen writes it: a part kept as an assembly's prototype,
    faces named by cadgen, the lower deviation held as a size below nominal."""
    found = read(CADGEN)
    by_name = {item["name"]: item for group in ("datums", "dimensions", "tolerances") for item in found[group]}
    assert len(by_name) == 12
    faces = lambda item, key="faces": [ref["face"] for ref in item[key]]
    assert [faces(by_name[d]) for d in "ABC"] == [[4], [1], [0]]
    assert (faces(by_name["thickness"]), faces(by_name["thickness"], "to")) == ([4], [2])
    assert by_name["thickness"]["tolerance"] == {"upper": 0.2, "lower": -0.2}
    assert by_name["hole-diameter"]["tolerance"] == {"upper": 0.1, "lower": 0.0}
    assert [by_name[n]["basic"] for n in ("thickness", "hole-from-B", "hole-from-C")] == [False, True, True]
    assert by_name["hole-position"]["datums"] == ["A", "B", "C"]
    assert faces(by_name["general"]) == [3, 5]
    assert all(ref.get("name", "").startswith("f:pmi_plate.") for item in by_name.values() for ref in item["faces"])
    assert [note["text"] for note in found["notes"]] == ["Remove all burrs and break sharp edges",
                                                         "Mask these features before coating with primer"]
    # A general note on the part; a flag note on the hole (cadgen's face 7) and on hole-diameter.
    assert found["notes"][0]["on"] == [{"part": 0}]
    assert [faces(item) for item in found["notes"][1]["on"] if "faces" in item] == [[6]]
    assert [item for item in found["notes"][1]["on"] if "faces" not in item] == [{"dimension": by_name["hole-diameter"]["id"]}]
    views = {view["name"]: view for view in found["views"]}
    assert views["A-A"]["clipped"] and views["A-A"]["shows"] == ["thickness", "hole-diameter", "hole-position", "hole-from-C"]
    assert len(views["iso"]["shows"]) == 12


def test_cadgen_material():
    """cadgen's material, with XCAF's density in g/cm³, carried as haecceity's material and unit."""
    from xcaf_pmi import to_haecceity

    assert read(CADGEN)["parts"][0]["material"] == {"name": "Alu_G6061_T6", "description": None,
                                                     "density": 2.7, "density_unit": "g/cm3"}
    doc = to_haecceity(read(CADGEN))["document"]
    assert doc["pmi"]["material"] == {"id": "Alu_G6061_T6", "name": None,
                                      "density": {"value": "2.7", "unit": "unit/g-per-cm3"}}
    assert doc["units"]["density"] == [{"id": "unit/g-per-cm3", "value": [["gram", "1."], ["centimetre", "-3."]]}]


def test_cadgen_step_leaves_material_to_haecceity(tmp_path):
    # OCCT's writer states density in gram³·cm²; the geometry STEP carries no material of its own.
    text = export_step(CADGEN, tmp_path / "plate.step").read_text(encoding="utf-8")
    assert "DERIVED_UNIT_ELEMENT" not in text and "'material name'" not in text


def test_cadgen_step_faces_follow_the_json(tmp_path):
    text = export_step(CADGEN, tmp_path / "plate.step").read_text(encoding="utf-8")
    assert re.findall(r"ADVANCED_FACE\(\s*'([^']*)'", text) == [f["name"] for f in read(CADGEN)["parts"][0]["faces"]]


def test_cadgen_plate_as_haecceity_json():
    from xcaf_pmi import to_haecceity

    mapped = to_haecceity(read(CADGEN))
    pmi = mapped["document"]["pmi"]
    assert mapped["document"]["schema"] == "haecceity.pmi/1"
    # The flag note is on the hole's face and on hole-diameter: haecceity.pmi/1 carries one owner.
    assert mapped["unmapped"] == ["note 0:1:9:1:2: also on dimension hole-diameter "
                                  "(a note has one owner, here feature feature/15)"]
    assert [len(pmi[k]) for k in ("datums", "dimensions", "tolerances", "notes")] == [3, 4, 5, 2]
    kinds = [t["value"]["kind"] for t in pmi["tolerances"]]
    assert kinds == ["flatness_tolerance", "position_tolerance"] + ["surface_profile_tolerance"] * 3
    assert [d["value"]["tolerance"] for d in pmi["dimensions"]][2:] == ["basic", "basic"]
    assert all(isinstance(i["face"], dict) and i["face"]["name"].startswith("f:pmi_plate.")
               for f in pmi["features"] for i in f["value"]["items"])
    assert [n["value"]["on"] for n in pmi["notes"]] == [None, {"feature": "feature/15"}]


needs_quiddity = pytest.mark.skipif(not os.environ.get("QUIDDITY"),
                                    reason="QUIDDITY: a quiddity binary built with --features json")


def _quiddity(*args):
    done = subprocess.run([os.environ["QUIDDITY"], "pmi", "json", *map(str, args)], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(done.stderr.strip())
    return json.loads(done.stdout)


def _round_trip(tmp_path, xbf, sent):
    """haecceity adds ``sent`` to the document's geometry; reading it back must give the same
    items, ids, faces and note owners (quiddity-rust#142's v1 contract)."""
    found = read(xbf)
    step = export_step(xbf, tmp_path / "geometry.step")
    (tmp_path / "pmi.json").write_text(json.dumps(sent))
    assert _quiddity("validate", tmp_path / "pmi.json")["valid"]
    assert _quiddity("import", step, tmp_path / "pmi.json", "-o", tmp_path / "out.step")["differences"] == []
    back = _quiddity("export", tmp_path / "out.step")["pmi"]

    index = {f["name"]: f["index"] for f in found["parts"][0]["faces"] if "name" in f}
    face = lambda a: a["face"] if isinstance(a["face"], int) else index[a["face"]["name"]]

    def faces_of(doc):
        features = {f["id"]: sorted(face(i) for i in f["value"]["items"]) for f in doc["features"]}
        on = lambda owner: owner and {k: features[v] if k == "feature" else v for k, v in owner.items()}
        return ({d["id"]: features.get(d["value"]["feature"]) for d in doc["datums"]}
                | {t["id"]: features[t["value"]["target"]["feature"]] for t in doc["tolerances"]}
                | {t["id"]: features.get(t["value"]["on"]) for t in doc["datum_targets"]}
                | {n["id"]: on(n["value"]["on"]) for n in doc["notes"]})

    for key in ("datums", "datum_targets", "dimensions", "tolerances", "notes"):
        assert [x["id"] for x in back[key]] == [x["id"] for x in sent["pmi"][key]], key
    assert faces_of(back) == faces_of(sent["pmi"])
    assert back["material"] == sent["pmi"]["material"]
    assert [d["value"]["tolerance"] for d in back["dimensions"]] == [d["value"]["tolerance"] for d in sent["pmi"]["dimensions"]]
    assert [n["value"]["text"] for n in back["notes"]] == [n["value"]["text"] for n in sent["pmi"]["notes"]]
    return back


@needs_quiddity
def test_haecceity_writes_it(tmp_path):
    """The whole route on cadgen's plate: its notes, the flag note on the hole's face."""
    from xcaf_pmi import to_haecceity

    _round_trip(tmp_path, CADGEN, to_haecceity(read(CADGEN))["document"])


def _without(doc, targets=False, item_notes=False):
    """The document less its datum targets, or less the notes owned by a dimension or tolerance."""
    doc = json.loads(json.dumps(doc))
    pmi = doc["pmi"]
    if targets:
        pmi["datums"] = [d for d in pmi["datums"] if not d["value"]["targets"]]
        pmi["datum_targets"] = []
    if item_notes:
        pmi["notes"] = [n for n in pmi["notes"] if not (n["value"]["on"] or {}).keys() & {"dimension", "tolerance"}]
    return doc


@needs_quiddity
def test_haecceity_writes_the_plate(plate, tmp_path):
    """The fit and the notes on a face and on the part, as haecceity writes them today."""
    from xcaf_pmi import to_haecceity

    _round_trip(tmp_path, plate, _without(to_haecceity(read(plate))["document"], targets=True, item_notes=True))


@needs_quiddity
def test_haecceity_writes_datum_targets(plate, tmp_path):
    """Datum targets keep their stated decimals through haecceity (fixed in quiddity 0.2.8)."""
    from xcaf_pmi import to_haecceity

    _round_trip(tmp_path, plate, _without(to_haecceity(read(plate))["document"], item_notes=True))


@needs_quiddity
def test_haecceity_writes_notes_on_gdt(plate, tmp_path):
    """Notes owned by a dimension or tolerance are written as AP242 allows (quiddity 0.2.8)."""
    from xcaf_pmi import to_haecceity

    _round_trip(tmp_path, plate, _without(to_haecceity(read(plate))["document"], targets=True))
