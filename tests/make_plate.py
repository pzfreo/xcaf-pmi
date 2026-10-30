"""A plate like text-to-cad's pmi_plate, with its GD&T made through OCCT's own XCAF API and
saved as an .xbf: the converter's fixture, built without cadgen."""

from __future__ import annotations

from pathlib import Path

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.PCDM import PCDM_StoreStatus
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.collections import Sequence_TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDimTolObjects import (
    XCAFDimTolObjects_DatumObject,
    XCAFDimTolObjects_DimensionObject,
    XCAFDimTolObjects_DimensionType,
    XCAFDimTolObjects_GeomToleranceObject,
    XCAFDimTolObjects_GeomToleranceType,
    XCAFDimTolObjects_GeomToleranceTypeValue,
)
from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_DocumentTool, XCAFDoc_Dimension, XCAFDoc_GeomTolerance


def _faces(shape):
    out, ex = [], TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return out


def build(path: Path) -> Path:
    plate = BRepPrimAPI_MakeBox(gp_Pnt(-50, -30, 0), 100, 60, 10).Shape()
    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), 5, 12).Shape()
    body = BRepAlgoAPI_Cut(plate, hole).Shape()

    app = XCAFApp_Application.GetApplication_s()
    BinXCAFDrivers.DefineFormat_s(app)
    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    app.InitDocument(doc)
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    dimtol = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    part = shapes.AddShape(body, False)
    TDataStd_Name.Set_s(part, TCollection_ExtendedString("plate"))

    def face(pick, name):
        f = pick(_faces(body))
        label = shapes.AddSubShape(part, f)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
        return label

    def centre(f):
        s = BRepAdaptor_Surface(f)
        u, v = (s.FirstUParameter() + s.LastUParameter()) / 2, (s.FirstVParameter() + s.LastVParameter()) / 2
        return s.Value(u, v)

    planes = [f for f in _faces(body) if BRepAdaptor_Surface(f).GetType() != GeomAbs_Cylinder]
    bottom = face(lambda fs: min(planes, key=lambda f: centre(f).Z()), "bottom")
    top = face(lambda fs: max(planes, key=lambda f: centre(f).Z()), "top")
    front = face(lambda fs: min(planes, key=lambda f: centre(f).Y()), "front")
    left = face(lambda fs: min(planes, key=lambda f: centre(f).X()), "left")
    bore = face(lambda fs: next(f for f in fs if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder), "hole")

    def seq(*labels):
        s = Sequence_TDF_Label()
        for label in labels:
            s.Append(label)
        return s

    datums = {}
    for letter, on in (("A", bottom), ("B", front), ("C", left)):
        label = dimtol.AddDatum()
        obj = XCAFDimTolObjects_DatumObject()
        obj.SetName(TCollection_HAsciiString(letter))
        XCAFDoc_Datum.Set_s(label).SetObject(obj)
        dimtol.SetDatum(seq(on), label)
        datums[letter] = label

    def dimension(kind, first, second, value, upper=None, lower=None):
        label = dimtol.AddDimension()
        obj = XCAFDimTolObjects_DimensionObject()
        obj.SetType(kind)
        obj.SetValue(value)
        if upper is not None:
            # XCAF's lower value is the size below nominal: 10 +0.2/-0.2 is upper 0.2, lower 0.2.
            obj.SetUpperTolValue(upper)
            obj.SetLowerTolValue(-lower)
        XCAFDoc_Dimension.Set_s(label).SetObject(obj)
        dimtol.SetDimension(seq(*first), seq(*second), label)
        return label

    T = XCAFDimTolObjects_DimensionType
    dimension(T.XCAFDimTolObjects_DimensionType_Location_LinearDistance, [bottom], [top], 10.0, 0.2, -0.2)
    dimension(T.XCAFDimTolObjects_DimensionType_Size_Diameter, [bore], [], 10.0, 0.1, 0.0)
    dimension(T.XCAFDimTolObjects_DimensionType_Location_LinearDistance, [front], [bore], 30.0)
    dimension(T.XCAFDimTolObjects_DimensionType_Location_LinearDistance, [left], [bore], 50.0)

    def tolerance(kind, on, value, refs=()):
        label = dimtol.AddGeomTolerance()
        obj = XCAFDimTolObjects_GeomToleranceObject()
        obj.SetType(kind)
        obj.SetValue(value)
        if kind == XCAFDimTolObjects_GeomToleranceType.XCAFDimTolObjects_GeomToleranceType_Position:
            obj.SetTypeOfValue(XCAFDimTolObjects_GeomToleranceTypeValue.XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
        XCAFDoc_GeomTolerance.Set_s(label).SetObject(obj)
        dimtol.SetGeomTolerance(on, label)
        for ref in refs:
            dimtol.SetDatumToGeomTol(datums[ref], label)
        return label

    G = XCAFDimTolObjects_GeomToleranceType
    tolerance(G.XCAFDimTolObjects_GeomToleranceType_Flatness, top, 0.05)
    tolerance(G.XCAFDimTolObjects_GeomToleranceType_Position, bore, 0.1, ("A", "B", "C"))

    path.parent.mkdir(parents=True, exist_ok=True)
    status = app.SaveAs(doc, TCollection_ExtendedString(str(path)))
    if status != PCDM_StoreStatus.PCDM_SS_OK:
        raise RuntimeError(f"saving {path}: {status}")
    app.Close(doc)
    return path


if __name__ == "__main__":
    import sys
    print(build(Path(sys.argv[1] if len(sys.argv) > 1 else "plate.xbf")))
