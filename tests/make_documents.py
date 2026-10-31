"""More test documents made through OCCT's own XCAF API: a plate with the tolerance modifiers,
zones and area datum target XCAF has, and a document of two parts with GD&T on each."""

from __future__ import annotations

from pathlib import Path

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.collections import Sequence_TDF_Label
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.PCDM import PCDM_StoreStatus
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDimTolObjects import (
    XCAFDimTolObjects_DatumObject as DatumObject,
    XCAFDimTolObjects_DatumTargetType as TargetType,
    XCAFDimTolObjects_DimensionObject as DimensionObject,
    XCAFDimTolObjects_DimensionType as DimensionType,
    XCAFDimTolObjects_GeomToleranceMatReqModif as MatReq,
    XCAFDimTolObjects_GeomToleranceModif as Modif,
    XCAFDimTolObjects_GeomToleranceObject as ToleranceObject,
    XCAFDimTolObjects_GeomToleranceType as ToleranceType,
    XCAFDimTolObjects_GeomToleranceTypeValue as TypeValue,
    XCAFDimTolObjects_GeomToleranceZoneModif as ZoneModif,
)
from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_DocumentTool, XCAFDoc_GeomTolerance


def _faces(shape):
    out, ex = [], TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(TopoDS.Face(ex.Current()))
        ex.Next()
    return out


def _seq(*labels):
    s = Sequence_TDF_Label()
    for label in labels:
        s.Append(label)
    return s


class _Document:
    def __init__(self):
        self.app = XCAFApp_Application.GetApplication_s()
        BinXCAFDrivers.DefineFormat_s(self.app)
        self.doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
        self.app.InitDocument(self.doc)
        self.shapes = XCAFDoc_DocumentTool.ShapeTool_s(self.doc.Main())
        self.dimtol = XCAFDoc_DocumentTool.DimTolTool_s(self.doc.Main())

    def part(self, shape, name):
        label = self.shapes.AddShape(shape, False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
        return label

    def face(self, part, face, name):
        label = self.shapes.AddSubShape(part, face)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(name))
        return label

    def datum(self, letter, *on):
        label = self.dimtol.AddDatum()
        obj = DatumObject()
        obj.SetName(TCollection_HAsciiString(letter))
        XCAFDoc_Datum.Set_s(label).SetObject(obj)
        if on:
            self.dimtol.SetDatum(_seq(*on), label)
        return label

    def tolerance(self, kind, on, value, name, refs=(), setup=lambda obj: None):
        label = self.dimtol.AddGeomTolerance()
        obj = ToleranceObject()
        obj.SetType(getattr(ToleranceType, f"XCAFDimTolObjects_GeomToleranceType_{kind}"))
        obj.SetValue(value)
        obj.SetSemanticName(TCollection_HAsciiString(name))
        setup(obj)
        XCAFDoc_GeomTolerance.Set_s(label).SetObject(obj)
        self.dimtol.SetGeomTolerance(on, label)
        for ref in refs:
            self.dimtol.SetDatumToGeomTol(ref, label)
        return label

    def dimension(self, kind, first, second, value, name, upper=0.1):
        label = self.dimtol.AddDimension()
        obj = DimensionObject()
        obj.SetType(getattr(DimensionType, f"XCAFDimTolObjects_DimensionType_{kind}"))
        obj.SetValue(value)
        obj.SetSemanticName(TCollection_HAsciiString(name))
        obj.SetUpperTolValue(upper)
        obj.SetLowerTolValue(upper)
        XCAFDoc_Dimension.Set_s(label).SetObject(obj)
        self.dimtol.SetDimension(_seq(*first), _seq(*second), label)
        return label

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.app.SaveAs(self.doc, TCollection_ExtendedString(str(path))) != PCDM_StoreStatus.PCDM_SS_OK:
            raise RuntimeError(f"saving {path}")
        self.app.Close(self.doc)
        return path


def _plate():
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    plate = BRepPrimAPI_MakeBox(gp_Pnt(-50, -30, 0), 100, 60, 10).Shape()
    hole = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), 5, 12).Shape()
    return BRepAlgoAPI_Cut(plate, hole).Shape()


def _centre(face):
    s = BRepAdaptor_Surface(face)
    return s.Value((s.FirstUParameter() + s.LastUParameter()) / 2, (s.FirstVParameter() + s.LastVParameter()) / 2)


def build_modifiers(path: Path) -> Path:
    """A plate whose tolerances carry XCAF's modifiers and zones, and a datum E of one area target
    whose area is held, as OCCT holds it, only as the target's shape."""
    d = _Document()
    body = _plate()
    part = d.part(body, "plate")
    planes = [f for f in _faces(body) if BRepAdaptor_Surface(f).GetType() != GeomAbs_Cylinder]
    bottom = d.face(part, min(planes, key=lambda f: _centre(f).Z()), "bottom")
    top_face = max(planes, key=lambda f: _centre(f).Z())
    top = d.face(part, top_face, "top")
    front = d.face(part, min(planes, key=lambda f: _centre(f).Y()), "front")
    bore = d.face(part, next(f for f in _faces(body) if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder), "hole")
    a, b = d.datum("A", bottom), d.datum("B", front)

    def modifiers(*names, material=None, maximum=None, zone=None, diameter=False):
        def setup(obj):
            for n in names:
                obj.AddModifier(getattr(Modif, f"XCAFDimTolObjects_GeomToleranceModif_{n}"))
            if material:
                obj.SetMaterialRequirementModifier(getattr(MatReq, f"XCAFDimTolObjects_GeomToleranceMatReqModif_{material}"))
            if maximum:
                obj.SetMaxValueModifier(maximum)
            if diameter:
                obj.SetTypeOfValue(TypeValue.XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
            if zone:
                obj.SetZoneModifier(getattr(ZoneModif, f"XCAFDimTolObjects_GeomToleranceZoneModif_{zone[0]}"))
                obj.SetValueOfZoneModifier(zone[1])
        return setup

    d.tolerance("Flatness", top, 0.05, "free-flat", setup=modifiers("Free_State"))
    d.tolerance("Parallelism", top, 0.1, "tangent-parallel", [a], setup=modifiers("Tangent_Plane"))
    d.tolerance("Position", bore, 0.2, "statistical-position", [a, b],
                setup=modifiers("Statistical_Tolerance", material="L", maximum=0.3, diameter=True))
    d.tolerance("ProfileOfSurface", front, 0.4, "around-profile", [a], setup=modifiers("All_Around"))
    d.tolerance("Straightness", bore, 0.02, "each-straight", setup=modifiers("Line_Element", "Common_Zone"))
    d.tolerance("CircularRunout", bore, 0.03, "angled-runout", [a], setup=modifiers(zone=("Runout", 30.0)))
    d.tolerance("Position", top, 0.5, "projected-position", [a], setup=modifiers(zone=("Projected", 8.0), diameter=True))
    # Datum E: one area target, its area the top face as the target's shape (no reference shapes).
    label = d.dimtol.AddDatum()
    obj = DatumObject()
    obj.SetName(TCollection_HAsciiString("E"))
    obj.IsDatumTarget(True)
    obj.SetDatumTargetType(TargetType.XCAFDimTolObjects_DatumTargetType_Area)
    obj.SetDatumTargetNumber(1)
    obj.SetDatumTarget(top_face)
    XCAFDoc_Datum.Set_s(label).SetObject(obj)
    d.tolerance("Perpendicularity", bore, 0.06, "on-area", [label])
    return d.save(path)


def build_two_parts(path: Path) -> Path:
    """A plate and a pin, two parts of one document, each with its datum, dimension and
    tolerance."""
    d = _Document()
    plate = _plate()
    pin_shape = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 4, 20).Shape()
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(100, 0, 0))
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    pin_shape = BRepBuilderAPI_Transform(pin_shape, move, True).Shape()
    first, second = d.part(plate, "plate"), d.part(pin_shape, "pin")
    planes = [f for f in _faces(plate) if BRepAdaptor_Surface(f).GetType() != GeomAbs_Cylinder]
    bottom = d.face(first, min(planes, key=lambda f: _centre(f).Z()), "plate-bottom")
    top = d.face(first, max(planes, key=lambda f: _centre(f).Z()), "plate-top")
    pin_faces = _faces(pin_shape)
    side = d.face(second, next(f for f in pin_faces if BRepAdaptor_Surface(f).GetType() == GeomAbs_Cylinder), "pin-side")
    end = d.face(second, min((f for f in pin_faces if BRepAdaptor_Surface(f).GetType() != GeomAbs_Cylinder),
                             key=lambda f: _centre(f).Z()), "pin-end")
    a = d.datum("A", bottom)
    d.dimension("Location_LinearDistance", [bottom], [top], 10.0, "plate-thickness")
    d.tolerance("Flatness", top, 0.05, "plate-flatness")
    p = d.datum("P", end)
    d.dimension("Size_Diameter", [side], [], 8.0, "pin-diameter", upper=0.02)
    d.tolerance("Perpendicularity", side, 0.04, "pin-perpendicularity", [p])
    return d.save(path)
