import json
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
    assert [d["name"] for d in found["datums"]] == ["A", "B", "C"]
    assert [named(d["faces"]) for d in found["datums"]] == [["bottom"], ["front"], ["left"]]
    dims = {(d["type"], d["value"]): d for d in found["dimensions"]}
    thickness = dims[("Location_LinearDistance", 10.0)]
    assert (named(thickness["faces"]), named(thickness["to"])) == (["bottom"], ["top"])
    assert thickness["tolerance"] == {"upper": 0.2, "lower": -0.2}
    assert dims[("Size_Diameter", 10.0)]["tolerance"] == {"upper": 0.1, "lower": 0.0}
    assert named(dims[("Location_LinearDistance", 30.0)]["to"]) == ["hole"]
    tols = {t["type"]: t for t in found["tolerances"]}
    assert tols["Flatness"]["value"] == 0.05 and named(tols["Flatness"]["faces"]) == ["top"]
    assert tols["Position"]["zone"] == "Diameter"
    assert tols["Position"]["datums"] == ["A", "B", "C"]


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
    in_step = re.findall(r"ADVANCED_FACE\('([^']*)'", text)
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
