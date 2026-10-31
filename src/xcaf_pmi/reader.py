"""Read an OCCT XCAF document's GD&T into a neutral intermediate form, and write its geometry
as a STEP without PMI.

The intermediate form keeps OCCT's own vocabulary (its enumeration names) and refers to faces
by the names the document gives them, with OCCT's face order and each face's geometry as a
fallback. Mapping it to haecceity's PMI JSON (quiddity-rust#142) is a separate step.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap, Sequence_TDF_Label
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.PCDM import PCDM_ReaderStatus
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_StepModelType
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.TopoDS import TopoDS
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDimTolObjects import XCAFDimTolObjects_DimensionFormVariance, XCAFDimTolObjects_DimensionGrade
from OCP.XCAFDoc import (
    XCAFDoc_Datum,
    XCAFDoc_DimTolTool,
    XCAFDoc_Dimension,
    XCAFDoc_DocumentTool,
    XCAFDoc_GeomTolerance,
    XCAFDoc_ShapeTool,
)
from OCP.XmlXCAFDrivers import XmlXCAFDrivers

FORMAT = "xcaf-pmi.intermediate/0"


def open_document(path: str | Path | bytes) -> TDocStd_Document:
    """Open an .xbf (BinXCAF) or .xml (XmlXCAF) document, from its path or its bytes.

    The document is read through the format's retrieval driver into one made here: OCP cannot
    hand back the document the application's ``Open`` fills (it rebinds a handle the binding
    copied), so that call leaves the Python-side document empty. cadgen reads its xbf this way.
    Bytes go through a temporary file: the drivers' stream reading expects the header the
    application's own ``Open`` has already read.
    """
    if isinstance(path, bytes):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            held = Path(folder) / ("document.xbf" if path.startswith(b"BINFILE") else "document.xml")
            held.write_bytes(path)
            return open_document(held)

    from OCP.BinXCAFDrivers import BinXCAFDrivers_DocumentRetrievalDriver
    from OCP.Message import Message_ProgressRange
    from OCP.XmlXCAFDrivers import XmlXCAFDrivers_DocumentRetrievalDriver

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xbf":
        driver, fmt = BinXCAFDrivers_DocumentRetrievalDriver(), "BinXCAF"
    elif suffix == ".xml":
        driver, fmt = XmlXCAFDrivers_DocumentRetrievalDriver(), "XmlXCAF"
    else:
        raise ValueError(f"{path.name}: not an XCAF document (.xbf or .xml)")
    app = XCAFApp_Application.GetApplication_s()
    BinXCAFDrivers.DefineFormat_s(app)
    XmlXCAFDrivers.DefineFormat_s(app)
    doc = TDocStd_Document(TCollection_ExtendedString(fmt))
    driver.Read(TCollection_ExtendedString(str(path), True), doc, app, None, Message_ProgressRange())
    if driver.GetStatus() != PCDM_ReaderStatus.PCDM_RS_OK:
        raise ValueError(f"{path}: OCCT cannot read it ({driver.GetStatus().name})")
    return doc


def _labels(fill) -> list:
    seq = Sequence_TDF_Label()
    fill(seq)
    return [seq.Value(i) for i in range(1, seq.Length() + 1)]


def _name(label) -> str | None:
    attr = TDataStd_Name()
    if label.IsAttribute(TDataStd_Name.GetID_s()) and label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return None


def _text(h) -> str | None:
    return None if h is None else h.ToCString()


def _enum(value) -> str:
    return value.name


def _xyz(v) -> list[float]:
    return [v.X(), v.Y(), v.Z()]


def _dumped(obj) -> dict[str, Any]:
    """An OCCT object's own ``DumpJson``: the fields OCP has no getter for."""
    out = io.BytesIO()
    obj.DumpJson(out)
    return json.loads("{" + out.getvalue().decode() + "}")


class _Faces:
    """Each part's faces in OCCT's order, and their names from the document."""

    def __init__(self, shapes: XCAFDoc_ShapeTool):
        self.parts: list[dict[str, Any]] = []
        self.labels: dict[str, int] = {}
        self._where: dict[int, tuple[int, list[int]]] = {}
        # Each part is a top-level shape that is not an assembly: an assembly's instances refer to
        # these prototypes, and GD&T is linked to the prototype's own sub-shape labels (cadgen
        # keeps even a single part as one instance of its prototype).
        parts = [label for label in _labels(shapes.GetShapes) if not XCAFDoc_ShapeTool.IsAssembly_s(label)]
        for p, label in enumerate(parts):
            shape = XCAFDoc_ShapeTool.GetShape_s(label)
            faces = ShapeMap()
            TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
            listed = [_face(TopoDS.Face(faces.FindKey(i)), i - 1) for i in range(1, faces.Extent() + 1)]
            self.parts.append({"name": _name(label), "faces": listed, "material": _material(label)})
            for sub in _labels(lambda s, l=label: XCAFDoc_ShapeTool.GetSubShapes_s(l, s)):
                index = faces.FindIndex(XCAFDoc_ShapeTool.GetShape_s(sub))
                if index:
                    if (name := _name(sub)) is not None:
                        listed[index - 1]["name"] = name
                    self._where[_key(sub)] = (p, [index - 1])
            self._where[_key(label)] = (p, list(range(faces.Extent())))
            self.labels[_key(label)] = p

    def ref(self, part: int, index: int) -> dict[str, Any]:
        face = self.parts[part]["faces"][index]
        return {"part": part, "face": index, **({"name": face["name"]} if "name" in face else {})}

    def refs(self, labels) -> list[dict[str, Any]]:
        out = []
        for label in labels:
            part, indices = self._where.get(_key(label), (None, []))
            if part is None:
                out.append({"unresolved": _name(label) or _entry(label)})
                continue
            out.extend(self.ref(part, i) for i in indices)
        return out


def _material(label) -> dict[str, Any] | None:
    """The material a part's label refers to (XCAF's material reference), with its density as
    XCAF holds it: a mass density in g/cm³."""
    from OCP.TDataStd import TDataStd_TreeNode
    from OCP.XCAFDoc import XCAFDoc, XCAFDoc_Material

    guid = XCAFDoc.MaterialRefGUID_s()
    node = TDataStd_TreeNode()
    if not (label.IsAttribute(guid) and label.FindAttribute(guid, node)) or node.Father() is None:
        return None
    material = XCAFDoc_Material()
    held = node.Father().Label()
    if not (held.IsAttribute(XCAFDoc_Material.GetID_s()) and held.FindAttribute(XCAFDoc_Material.GetID_s(), material)):
        return None
    density = material.GetDensity()
    return {
        "name": _text(material.GetName()),
        "description": _text(material.GetDescription()) or None,
        "density": density if density > 0 else None,
        "density_unit": "g/cm3",
    }


def _key(label) -> str:
    return _entry(label)


def _entry(label) -> str:
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDF import TDF_Tool
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _face(face, index: int) -> dict[str, Any]:
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    c = props.CentreOfMass()
    return {
        "index": index,
        "surface": _enum(BRepAdaptor_Surface(face).GetType()).removeprefix("GeomAbs_").lower(),
        "area": round(props.Mass(), 6),
        "centroid": [round(c.X(), 6), round(c.Y(), 6), round(c.Z(), 6)],
    }


def read(path: str | Path | bytes) -> dict[str, Any]:
    """The document's parts, faces and GD&T, in OCCT's terms."""
    return read_document(open_document(path), "<bytes>" if isinstance(path, bytes) else str(path))


def read_document(doc: TDocStd_Document, source: str) -> dict[str, Any]:
    """``read`` on a document already open."""
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    faces = _Faces(shapes)
    unread: list[str] = []

    def on(label):
        first, second = Sequence_TDF_Label(), Sequence_TDF_Label()
        XCAFDoc_DimTolTool.GetRefShapeLabel_s(label, first, second)
        seq = lambda s: [s.Value(i) for i in range(1, s.Length() + 1)]
        return faces.refs(seq(first)), faces.refs(seq(second))

    datums = []
    for label in _labels(tool.GetDatumLabels):
        if not label.IsAttribute(XCAFDoc_Datum.GetID_s()):
            unread.append(f"datum {_entry(label)}: no datum object")
            continue
        # Set_s hands back the label's own attribute (checked present above, so nothing is
        # made); FindAttribute fills a detached copy whose object OCP cannot reach.
        obj = XCAFDoc_Datum.Set_s(label).GetObject()
        first, _ = on(label)
        # OCCT keeps each datum target as a datum of its own, named as its datum and numbered.
        target = None
        if obj.IsDatumTarget():
            target = {"type": _enum(obj.GetDatumTargetType()).removeprefix("XCAFDimTolObjects_DatumTargetType_"),
                      "number": obj.GetDatumTargetNumber()}
            if obj.HasDatumTargetParams():
                axis = obj.GetDatumTargetAxis()
                target |= {"length": obj.GetDatumTargetLength(), "width": obj.GetDatumTargetWidth(),
                           "origin": _xyz(axis.Location()), "axis": _xyz(axis.Direction()),
                           "x": _xyz(axis.XDirection())}
        datums.append({
            "id": _entry(label),
            "name": _text(obj.GetName()),
            "modifiers": [_enum(m) for m in obj.GetModifiers()],
            "target": target,
            "faces": first,
        })
    by_entry = {d["id"]: d["name"] for d in datums}

    dimensions = []
    for label in _labels(tool.GetDimensionLabels):
        if not label.IsAttribute(XCAFDoc_Dimension.GetID_s()):
            unread.append(f"dimension {_entry(label)}: no dimension object")
            continue
        obj = XCAFDoc_Dimension.Set_s(label).GetObject()
        first, second = on(label)
        item: dict[str, Any] = {
            "id": _entry(label),
            "name": _text(obj.GetSemanticName()),
            "type": _enum(obj.GetType()).removeprefix("XCAFDimTolObjects_DimensionType_"),
            "value": obj.GetValue(),
            "faces": first,
            "to": second,
            "modifiers": [_enum(m) for m in obj.GetModifiers()],
        }
        if obj.IsDimWithPlusMinusTolerance():
            # XCAF holds the lower deviation as its size below nominal (OCCT's STEP writer negates
            # it): reported signed, as the STEP states it (10 +0.2/-0.2: upper 0.2, lower -0.2).
            item["tolerance"] = {"upper": obj.GetUpperTolValue(), "lower": -obj.GetLowerTolValue() + 0.0}
        elif obj.IsDimWithRange():
            item["range"] = {"lower": obj.GetLowerBound(), "upper": obj.GetUpperBound()}
        if obj.IsDimWithClassOfTolerance():
            # GetClassOfTolerance returns its values through references OCP cannot fill; the
            # object's DumpJson states them. A class may stand beside a ± tolerance (H7 +0.015/0).
            held = _dumped(obj)
            item["fit"] = {
                "hole": bool(held["IsHole"]),
                "letter": _enum(XCAFDimTolObjects_DimensionFormVariance(held["FormVariance"]))
                .removeprefix("XCAFDimTolObjects_DimensionFormVariance_"),
                "grade": _enum(XCAFDimTolObjects_DimensionGrade(held["Grade"])).removeprefix("XCAFDimTolObjects_DimensionGrade_"),
            }
        if obj.HasDescriptions():
            item["descriptions"] = [[_text(obj.GetDescriptionName(i)), _text(obj.GetDescription(i))]
                                    for i in range(obj.NbDescriptions())]
        # AP242's mark of a basic (theoretically exact) dimension, as cadgen and Specify write it.
        item["basic"] = ["dimensional note", "theoretical"] in item.get("descriptions", [])
        if obj.HasQualifier():
            item["qualifier"] = _enum(obj.GetQualifier())
        dimensions.append(item)

    tolerances = []
    for label in _labels(tool.GetGeomToleranceLabels):
        if not label.IsAttribute(XCAFDoc_GeomTolerance.GetID_s()):
            unread.append(f"tolerance {_entry(label)}: no tolerance object")
            continue
        obj = XCAFDoc_GeomTolerance.Set_s(label).GetObject()
        first, _ = on(label)
        refs = _labels(lambda s, l=label: XCAFDoc_DimTolTool.GetDatumOfTolerLabels_s(l, s))
        tolerances.append({
            "id": _entry(label),
            "name": _text(obj.GetSemanticName()),
            "type": _enum(obj.GetType()).removeprefix("XCAFDimTolObjects_GeomToleranceType_"),
            "value": obj.GetValue(),
            "zone": _enum(obj.GetTypeOfValue()).removeprefix("XCAFDimTolObjects_GeomToleranceTypeValue_"),
            "material": _enum(obj.GetMaterialRequirementModifier()).removeprefix("XCAFDimTolObjects_GeomToleranceMatReqModif_"),
            "modifiers": [_enum(m) for m in obj.GetModifiers()],
            "datums": [by_entry.get(_entry(r), _entry(r)) for r in refs],
            "faces": first,
        })

    names = {item["id"]: item.get("name") for group in (datums, dimensions, tolerances) for item in group}
    kinds = {item["id"]: kind for kind, group in (("datum", datums), ("dimension", dimensions),
                                                  ("tolerance", tolerances)) for item in group}

    notes = []
    if XCAFDoc_DocumentTool.CheckNotesTool_s(doc.Main()):
        from OCP.TDF import TDF_Label, TDF_Tool
        from OCP.XCAFDoc import XCAFDoc_AssemblyItemRef, XCAFDoc_NoteComment

        notes_tool = XCAFDoc_DocumentTool.NotesTool_s(doc.Main())

        def annotated(ref) -> dict[str, Any]:
            """What an annotated item is: faces, a GD&T item (by its entry) or a whole part."""
            # An item is a path of labels (an assembly's occurrences down to the item); its last
            # label is the item, and a component stands for the part it instances.
            label = TDF_Label()
            TDF_Tool.Label_s(doc.GetData(), ref.GetItem().GetPath().Last(), label)
            if XCAFDoc_ShapeTool.IsReference_s(label):
                referred = TDF_Label()
                XCAFDoc_ShapeTool.GetReferredShape_s(label, referred)
                label = referred
            entry = _entry(label)
            if ref.IsSubshapeIndex():
                # The index is the face's in its part's map of faces (1-based), as cadgen writes it.
                index, part = ref.GetSubshapeIndex(), faces.labels.get(entry)
                if part is None or not 1 <= index <= len(faces.parts[part]["faces"]):
                    return {"faces": [{"unresolved": f"{entry} sub-shape {index}"}]}
                return {"faces": [faces.ref(part, index - 1)]}
            if entry in kinds:
                return {kinds[entry]: entry}
            if entry in faces.labels:
                return {"part": faces.labels[entry]}
            return {"faces": faces.refs([label])}

        attached: dict[str, list[dict[str, Any]]] = {}
        for item in _labels(notes_tool.GetAnnotatedItems):
            if not item.IsAttribute(XCAFDoc_AssemblyItemRef.GetID_s()):
                unread.append(f"annotated item {_entry(item)}: no item reference")
                continue
            ref = XCAFDoc_AssemblyItemRef.Get_s(item)
            found = Sequence_TDF_Label()
            # Notes on an item, on one attribute of it (taken as on the item) or on a sub-shape.
            if ref.IsSubshapeIndex():
                notes_tool.GetSubshapeNotes(ref.GetItem(), ref.GetSubshapeIndex(), found)
            elif ref.IsGUID():
                notes_tool.GetAttrNotes(ref.GetItem(), ref.GetGUID(), found)
            else:
                notes_tool.GetNotes(ref.GetItem(), found)
            what = annotated(ref)
            for i in range(1, found.Length() + 1):
                attached.setdefault(_entry(found.Value(i)), []).append(what)

        for label in _labels(notes_tool.GetNotes):
            if not label.IsAttribute(XCAFDoc_NoteComment.GetID_s()):
                unread.append(f"note {_entry(label)}: not a comment note")
                continue
            notes.append({"id": _entry(label), "name": _name(label),
                          "text": XCAFDoc_NoteComment.Get_s(label).Comment().ToExtString(),
                          "on": attached.get(_entry(label), [])})

    views = []
    if XCAFDoc_DocumentTool.CheckViewTool_s(doc.Main()):
        from OCP.XCAFDoc import XCAFDoc_View

        view_tool = XCAFDoc_DocumentTool.ViewTool_s(doc.Main())
        for label in _labels(view_tool.GetViewLabels):
            obj = XCAFDoc_View.Set_s(label).GetObject()
            point, direction, up = obj.ProjectionPoint(), obj.ViewDirection(), obj.UpDirection()
            shown = _labels(lambda seq, l=label: view_tool.GetRefGDTLabel(l, seq))
            views.append({
                "id": _entry(label),
                "name": _text(obj.Name()),
                "projection": _enum(obj.Type()).removeprefix("XCAFView_ProjectionType_"),
                "point": [point.X(), point.Y(), point.Z()],
                "direction": [direction.X(), direction.Y(), direction.Z()],
                "up": [up.X(), up.Y(), up.Z()],
                "shows": [names.get(_entry(g)) or _entry(g) for g in shown],
                "notes": [_name(n) or _entry(n) for n in _labels(lambda seq, l=label: view_tool.GetRefNoteLabel(l, seq))],
                "clipped": bool(_labels(lambda seq, l=label: view_tool.GetRefClippingPlaneLabel(l, seq))),
            })

    return {
        "format": FORMAT,
        "source": source,
        "parts": faces.parts,
        "datums": datums,
        "dimensions": dimensions,
        "tolerances": tolerances,
        "notes": notes,
        "views": views,
        "unread": unread,
    }


def export_step(path: str | Path | bytes, output: str | Path) -> Path:
    """The document's geometry, names and colours as AP242 STEP, without its GD&T: the file the
    PMI JSON's faces refer to, for haecceity to add the PMI to."""
    output = Path(output)
    output.write_bytes(geometry_step(open_document(path)))
    return output


def geometry_step(doc: TDocStd_Document) -> bytes:
    """``export_step`` on a document already open, as the STEP's bytes (no file written)."""
    # OCCT's translator reports its progress on stdout; a caller writing JSON there needs it quiet.
    from OCP.Message import Message, Message_Printer
    Message.DefaultMessenger_s().RemovePrinters(Message_Printer.get_type_descriptor_s())
    writer = STEPCAFControl_Writer()
    # The writer defines the translator's parameters: set them once it exists (as cadgen does).
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetIVal_s("write.stepcaf.subshapes.name", 1)
    writer.SetNameMode(True)
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    # Material is left to haecceity (to_haecceity carries it): OCCT's writer states a density's unit
    # as gram³·cm² (DERIVED_UNIT_ELEMENT exponents 3 and 2), which readers rightly ignore.
    writer.SetMaterialMode(False)
    writer.SetVisualMaterialMode(True)
    writer.SetDimTolMode(False)
    if not writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs):
        raise RuntimeError("OCCT could not transfer the document to STEP")
    out = io.BytesIO()
    if writer.WriteStream(out) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError("OCCT could not write the STEP")
    return out.getvalue()
