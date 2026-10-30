"""Read an OCCT XCAF document's GD&T into a neutral intermediate form, and write its geometry
as a STEP without PMI.

The intermediate form keeps OCCT's own vocabulary (its enumeration names) and refers to faces
by the names the document gives them, with OCCT's face order and each face's geometry as a
fallback. Mapping it to haecceity's PMI JSON (quiddity-rust#142) is a separate step.
"""

from __future__ import annotations

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


def open_document(path: str | Path) -> TDocStd_Document:
    """Open an .xbf (BinXCAF) or .xml (XmlXCAF) document.

    The document is read through the format's retrieval driver into one made here: OCP cannot
    hand back the document the application's ``Open`` fills (it rebinds a handle the binding
    copied), so that call leaves the Python-side document empty. cadgen reads its xbf this way.
    """
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


class _Faces:
    """Each part's faces in OCCT's order, and their names from the document."""

    def __init__(self, shapes: XCAFDoc_ShapeTool):
        self.parts: list[dict[str, Any]] = []
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
            self.parts.append({"name": _name(label), "faces": listed})
            for sub in _labels(lambda s, l=label: XCAFDoc_ShapeTool.GetSubShapes_s(l, s)):
                index = faces.FindIndex(XCAFDoc_ShapeTool.GetShape_s(sub))
                if index:
                    if (name := _name(sub)) is not None:
                        listed[index - 1]["name"] = name
                    self._where[_key(sub)] = (p, [index - 1])
            self._where[_key(label)] = (p, list(range(faces.Extent())))

    def refs(self, labels) -> list[dict[str, Any]]:
        out = []
        for label in labels:
            part, indices = self._where.get(_key(label), (None, []))
            if part is None:
                out.append({"unresolved": _name(label) or _entry(label)})
                continue
            for i in indices:
                face = self.parts[part]["faces"][i]
                out.append({"part": part, "face": i, **({"name": face["name"]} if "name" in face else {})})
        return out


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


def read(path: str | Path) -> dict[str, Any]:
    """The document's parts, faces and GD&T, in OCCT's terms."""
    doc = open_document(path)
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
        datums.append({
            "id": _entry(label),
            "name": _text(obj.GetName()),
            "modifiers": [_enum(m) for m in obj.GetModifiers()],
            "target": bool(obj.IsDatumTarget()),
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
        elif obj.IsDimWithClassOfTolerance():
            unread.append(f"dimension {item['id']}: class of tolerance (fit) not read yet")
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

    notes = []
    if XCAFDoc_DocumentTool.CheckNotesTool_s(doc.Main()):
        from OCP.XCAFDoc import XCAFDoc_NoteComment

        notes_tool = XCAFDoc_DocumentTool.NotesTool_s(doc.Main())
        for label in _labels(notes_tool.GetNotes):
            if not label.IsAttribute(XCAFDoc_NoteComment.GetID_s()):
                unread.append(f"note {_entry(label)}: not a comment note")
                continue
            notes.append({"id": _entry(label), "name": _name(label),
                          "text": XCAFDoc_NoteComment.Get_s(label).Comment().ToExtString()})
        if notes:
            unread.append("notes: what each note is attached to is not read yet")

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
        "source": str(path),
        "parts": faces.parts,
        "datums": datums,
        "dimensions": dimensions,
        "tolerances": tolerances,
        "notes": notes,
        "views": views,
        "unread": unread,
    }


def export_step(path: str | Path, output: str | Path) -> Path:
    """The document's geometry, names and colours as AP242 STEP, without its GD&T: the file the
    PMI JSON's faces refer to, for haecceity to add the PMI to."""
    doc = open_document(path)
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
    writer.SetDimTolMode(False)
    if not writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs):
        raise RuntimeError(f"{path}: OCCT could not transfer the document to STEP")
    if writer.Write(str(output)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise RuntimeError(f"{output}: OCCT could not write the STEP")
    return Path(output)
