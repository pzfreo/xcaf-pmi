"""The part's manufacturing process, between XCAF named data and Specify's STEP UDA."""

import re

import pytest
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_NamedData
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from quiddity import pmi

from make_documents import _Document
from xcaf_pmi import NotCarriedOver, open_document, save, to_step, to_xcaf
from xcaf_pmi.cli import main
from xcaf_pmi.process import DEFAULT, KEY, OPTIONS
from xcaf_pmi.reader import _labels, geometry_step, read_document


def _set(label, key, value):
    TDataStd_NamedData.Set_s(label).SetString(TCollection_ExtendedString(key),
                                           TCollection_ExtendedString(value))


def _document(*values):
    d = _Document()
    for i, value in enumerate(values):
        label = d.part(BRepPrimAPI_MakeBox(i + 1, 2, 3).Shape(), f"part-{i}")
        if value is not None:
            _set(label, KEY, value)
    return d


def _part_labels(doc):
    return _labels(XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).GetShapes)


def _attributes(step, part=None):
    return [a["value"] for a in pmi.read(step, part=part)["pmi"]["attributes"]]


def _assert_process(step, value, marked=False, part=None):
    [a] = _attributes(step, part)
    assert a["name"] == "specify process"
    assert a["description"] == "user defined attribute"
    assert a["on"] is None
    assert a["general_property"] == {"id": "", "name": "specify process", "description": None}
    assert a["items"] == [[KEY, {"text": value}]] + ([[DEFAULT, {"text": "true"}]] if marked else [])


def _specified_step(*, marked=False, key=KEY, value="3D printed: FDM", name="specify process", extra=False):
    """Insert the contract's literal entities, independently of the process mapping and writer."""
    step = geometry_step(_document(None).doc).decode()
    pd = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\(", step)[1]
    context = re.search(r"#(\d+)\s*=\s*\([^;]*REPRESENTATION_CONTEXT\(", step)[1]
    start = max(map(int, re.findall(r"#(\d+)\s*=", step))) + 1
    refs = [f"#{start}"]
    entities = [f"#{start}=DESCRIPTIVE_REPRESENTATION_ITEM('{key}','{value}');"]
    if marked:
        refs.append(f"#{start + 6}")
        entities.append(f"#{start + 6}=DESCRIPTIVE_REPRESENTATION_ITEM('{DEFAULT}','true');")
    if extra:
        refs.append(f"#{start + 7}")
        entities.append(f"#{start + 7}=DESCRIPTIVE_REPRESENTATION_ITEM('other','kept');")
    entities += [f"#{start + 1}=REPRESENTATION('',({','.join(refs)}),#{context});",
                 f"#{start + 2}=PROPERTY_DEFINITION('{name}','user defined attribute',#{pd});",
                 f"#{start + 3}=PROPERTY_DEFINITION_REPRESENTATION(#{start + 2},#{start + 1});",
                 f"#{start + 4}=GENERAL_PROPERTY('','{name}',$);",
                 f"#{start + 5}=GENERAL_PROPERTY_ASSOCIATION('',$,#{start + 4},#{start + 2});"]
    return step.replace("ENDSEC;\nEND-ISO-10303-21;", "\n".join(entities) + "\nENDSEC;\nEND-ISO-10303-21;").encode()


def test_code_first_process_is_one_set_on_the_product_definition(tmp_path):
    d = _document("3D printed: FDM")
    xbf = d.save(tmp_path / "part.xbf")
    step, report = to_step(xbf, strict=True, report=True)
    assert report["unmapped"] == [] and report["quiddity"]["differences"] == []
    _assert_process(step, "3D printed: FDM")
    text = step.decode()
    [pd] = re.findall(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\(", text)
    [prop] = re.findall(r"#(\d+)=PROPERTY_DEFINITION\('specify process','user defined attribute',#" + pd + r"\);", text)
    assert re.search(r"PROPERTY_DEFINITION_REPRESENTATION\(#" + prop + r",#\d+\)", text)
    assert len(re.findall(r"PROPERTY_DEFINITION\('specify process'", text)) == 1
    assert DEFAULT.encode() not in step
    again = save(to_xcaf(step), tmp_path / "again.xbf")
    doc = open_document(again)
    data = TDataStd_NamedData.Set_s(_part_labels(doc)[0])
    assert data.GetString(TCollection_ExtendedString(KEY)).ToExtString() == "3D printed: FDM"
    _assert_process(to_step(again, strict=True), "3D printed: FDM")


@pytest.mark.parametrize("value", OPTIONS)
def test_every_process_option(value):
    _assert_process(to_step(_document(value.swapcase()).doc, strict=True), value)


@pytest.mark.parametrize("marked", [False, True])
def test_specify_answer_and_accepted_suggestion_round_trip(marked, tmp_path):
    step = _specified_step(marked=marked)
    doc = to_xcaf(step)
    data = TDataStd_NamedData.Set_s(_part_labels(doc)[0])
    assert data.GetString(TCollection_ExtendedString(KEY)).ToExtString() == "3D printed: FDM"
    assert data.HasString(TCollection_ExtendedString(DEFAULT)) == marked
    if marked:
        assert data.GetString(TCollection_ExtendedString(DEFAULT)).ToExtString() == "true"
    xbf = save(doc, tmp_path / "part.xbf")
    written, report = to_step(xbf, strict=True, report=True)
    assert report["unmapped"] == [] and report["quiddity"]["differences"] == []
    _assert_process(written, "3D printed: FDM", marked)


@pytest.mark.parametrize("key", [KEY, "MANUFACTURING_PROCESS", "Manufacturing Process", "manufacturing-process"])
def test_read_process_from_any_part_attribute_set(key):
    doc = to_xcaf(_specified_step(key=key, value="3d PRINTED: fdm", name="another set"))
    assert read_document(doc, "<document>")["parts"][0][KEY] == "3D printed: FDM"
    _assert_process(to_step(doc, strict=True), "3D printed: FDM")


def test_invalid_step_process_is_not_read_as_the_process():
    doc = to_xcaf(_specified_step(value="laser cut"))
    assert KEY not in read_document(doc, "<document>")["parts"][0]


def test_invalid_named_data_is_reported_and_strict_writes_nothing(tmp_path, capsys):
    xbf = _document("laser cut").save(tmp_path / "invalid.xbf")
    step, report = to_step(xbf, report=True)
    assert _attributes(step) == []
    [problem] = report["unmapped"]
    assert "manufacturing process 'laser cut'" in problem
    with pytest.raises(NotCarriedOver) as refused:
        to_step(xbf, strict=True)
    assert refused.value.unmapped == [problem]
    out = tmp_path / "out.step"
    assert main(["to-step", str(xbf), "-o", str(out)]) == 0
    assert f"not carried over: {problem}" in capsys.readouterr().err
    assert _attributes(out) == []
    strict = tmp_path / "strict.step"
    assert main(["to-step", str(xbf), "-o", str(strict), "--strict"]) == 3
    assert problem in capsys.readouterr().err
    assert not strict.exists()


def test_each_process_only_part_and_part_selection():
    d = _document("machined", "3D printed: FDM")
    step = to_step(d.doc, strict=True)
    _assert_process(step, "machined", part=0)
    _assert_process(step, "3D printed: FDM", part=1)
    selected = to_step(d.doc, part=1, strict=True)
    assert _attributes(selected, 0) == []
    _assert_process(selected, "3D printed: FDM", part=1)
    again = to_step(to_xcaf(step), strict=True)
    _assert_process(again, "machined", part=0)
    _assert_process(again, "3D printed: FDM", part=1)


def test_invalid_process_on_another_part_is_reported():
    d = _document("machined", "unknown")
    _, report = to_step(d.doc, report=True)
    assert len(report["unmapped"]) == 1
    assert report["unmapped"][0].startswith("part 1: manufacturing process 'unknown'")
    with pytest.raises(NotCarriedOver):
        to_step(d.doc, strict=True)
    to_step(d.doc, part=0, strict=True)


@pytest.mark.parametrize("value", ["cast", "unknown", None])
def test_edited_or_removed_process_does_not_restore_a_stale_uda(value):
    doc = to_xcaf(_specified_step(marked=True))
    data = TDataStd_NamedData.Set_s(_part_labels(doc)[0])
    if value is None:
        strings = data.GetStringsContainer()
        strings.UnBind(TCollection_ExtendedString(KEY))
        data.ChangeStrings(strings)
    else:
        _set(_part_labels(doc)[0], KEY, value)
    step, report = to_step(doc, report=True)
    if value == "cast":
        _assert_process(step, "cast", marked=True)
        assert report["unmapped"] == []
    else:
        assert _attributes(step) == []
        assert bool(report["unmapped"]) == (value == "unknown")


def test_other_items_in_the_process_set_are_kept():
    doc = to_xcaf(_specified_step(marked=True, extra=True))
    written, report = to_step(doc, strict=True, report=True)
    assert report["unmapped"] == [] and report["quiddity"]["differences"] == []
    [attribute] = _attributes(written)
    items = attribute["items"]
    assert sorted(items) == sorted([[KEY, {"text": "3D printed: FDM"}], [DEFAULT, {"text": "true"}],
                                   ["other", {"text": "kept"}]])
