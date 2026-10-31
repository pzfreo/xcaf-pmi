"""Build an XCAF document's GD&T from haecceity's PMI JSON (``haecceity.pmi/1``) and its
presentation (``haecceity.presentation/1``): the reverse of ``to_haecceity``, using its tables.

The document already holds the part's geometry (``geometry.read_step``). Each item is anchored
to the part's faces (and edges) as haecceity numbers them, through ``faces``, the map from
haecceity's face indices to OCCT's. Values are converted to millimetres and degrees, the units
OCCT's reader gives the geometry.

XCAF keeps a datum's modifiers and its place in a datum system on the datum itself. A datum is
therefore one XCAF datum, on its feature, and tolerances that refer to it plainly share it; a
reference with modifiers, or two datums in one compartment (A-B), is a datum of its own for that
tolerance, named as its datum, with its modifiers and its compartment as its position (as OCCT's
own reader makes them). Each datum target is a datum of its own, named as its datum.

What has no place in XCAF is listed in ``unmapped``, never dropped silently.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRep import BRep_Builder
from OCP.collections import (
    Sequence_TDF_Label,
    Sequence_XCAFDimTolObjects_DatumSingleModif,
    Sequence_XCAFDimTolObjects_DimensionModif,
)
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.Standard import Standard_GUID
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDataStd import TDataStd_AsciiString, TDataStd_Name
from OCP.TopoDS import TopoDS_Compound
from OCP.XCAFDimTolObjects import (
    XCAFDimTolObjects_AngularQualifier as AngularQualifier,
    XCAFDimTolObjects_DatumModifWithValue as DatumModifWithValue,
    XCAFDimTolObjects_DatumObject,
    XCAFDimTolObjects_DatumSingleModif as DatumSingleModif,
    XCAFDimTolObjects_DatumTargetType as DatumTargetType,
    XCAFDimTolObjects_DimensionFormVariance as FormVariance,
    XCAFDimTolObjects_DimensionGrade as Grade,
    XCAFDimTolObjects_DimensionModif as DimensionModif,
    XCAFDimTolObjects_DimensionObject,
    XCAFDimTolObjects_DimensionQualifier as DimensionQualifier,
    XCAFDimTolObjects_DimensionType as DimensionType,
    XCAFDimTolObjects_GeomToleranceMatReqModif as MatReqModif,
    XCAFDimTolObjects_GeomToleranceModif as GeomToleranceModif,
    XCAFDimTolObjects_GeomToleranceObject,
    XCAFDimTolObjects_GeomToleranceType as GeomToleranceType,
    XCAFDimTolObjects_GeomToleranceTypeValue as TypeValue,
    XCAFDimTolObjects_GeomToleranceZoneModif as ZoneModif,
)
from OCP.XCAFDoc import (
    XCAFDoc_Datum,
    XCAFDoc_Dimension,
    XCAFDoc_DocumentTool,
    XCAFDoc_GeomTolerance,
    XCAFDoc_ShapeTool,
)

from xcaf_pmi.haecceity import (
    ANGLE, DATUM_MODIFIER, DATUM_MODIFIER_WITH_VALUE, DIMENSION_MODIFIER, LOCATION, MATERIAL, QUALIFIER, SIZE,
    TOLERANCE, TOLERANCE_MODIFIER,
)

# Each table of ``to_haecceity``, the other way round: haecceity's name to OCCT's.
_SIZE = {v: k for k, v in SIZE.items()}
_LOCATION = {v: k for k, v in LOCATION.items()}
_TOLERANCE = {v: k for k, v in TOLERANCE.items()}
_MATERIAL = {v: k for k, v in MATERIAL.items() if v}
_TOLERANCE_MODIFIER = {v: k for k, v in TOLERANCE_MODIFIER.items()}
_DIMENSION_MODIFIER = {v: k for k, v in DIMENSION_MODIFIER.items()}
_DATUM_MODIFIER = {v: k for k, v in DATUM_MODIFIER.items()}
_DATUM_MODIFIER_WITH_VALUE = {v: k for k, v in DATUM_MODIFIER_WITH_VALUE.items()}
_QUALIFIER = {v: k for k, v in QUALIFIER.items()}
_ANGLE = {v: k for k, v in ANGLE.items()}
# haecceity's zone forms that XCAF states as a diameter sign.
_DIAMETER = {"cylindrical or circular": "Diameter", "within a circle": "Diameter", "within a cylinder": "Diameter",
             "spherical": "SphericalDiameter", "within a sphere": "SphericalDiameter"}

MM = {"millimetre": 1.0, "micrometre": 0.001, "centimetre": 10.0, "metre": 1000.0, "inch": 25.4, "foot": 304.8}
DEGREES = {"degree": 1.0, "radian": 57.29577951308232}
# Mass in grams and length in centimetres: XCAF holds a density in g/cm³.
_GRAMS = {"gram": 1.0, "kilogram": 1000.0, "milligram": 0.001, "pound": 453.59237, "tonne": 1e6}
_CENTIMETRES = {"centimetre": 1.0, "millimetre": 0.1, "metre": 100.0, "inch": 2.54, "foot": 30.48,
                "micrometre": 1e-4}


def _enum(enum, prefix: str, name: str):
    return getattr(enum, f"{prefix}_{name}")


def _text(value: str | None) -> TCollection_HAsciiString:
    return TCollection_HAsciiString(value or "")


def _seq(labels) -> Sequence_TDF_Label:
    out = Sequence_TDF_Label()
    for label in labels:
        out.Append(label)
    return out


class _Units:
    """The document's units, by id: a length in millimetres, an angle in degrees."""

    def __init__(self, units: dict[str, Any]):
        self.length = {u["id"]: self._factor(u["value"], MM, "metres", 1000.0) for u in units["length"]}
        self.angle = {u["id"]: self._factor(u["value"], DEGREES, "radians", DEGREES["radian"]) for u in units["angle"]}
        self.density = {u["id"]: u["value"] for u in units["density"]}

    @staticmethod
    def _factor(value, known: dict[str, float], key: str, per: float) -> float | None:
        if isinstance(value, str):
            return known.get(value)
        return float(value["other"][key]) * per

    def value(self, value: dict[str, Any] | None) -> float | None:
        """A haecceity value (a length or an angle) in millimetres or degrees."""
        if value is None:
            return None
        (kind, quantity), = value["quantity"].items()
        factor = (self.length if kind == "length" else self.angle).get(quantity["unit"])
        return None if factor is None else float(Decimal(quantity["value"]) * Decimal(repr(factor)))

    def length_of(self, quantity: dict[str, Any]) -> float | None:
        factor = self.length.get(quantity["unit"])
        return None if factor is None else float(quantity["value"]) * factor

    def grams_per_cm3(self, density: dict[str, Any]) -> float | None:
        factor = 1.0
        for name, exponent in self.density.get(density["unit"], []):
            e = float(exponent)
            if name in _GRAMS:
                factor *= _GRAMS[name] ** e
            elif name in _CENTIMETRES:
                factor *= _CENTIMETRES[name] ** e
            else:
                return None
        return float(density["value"]) * factor


def build(doc, part, document: dict[str, Any], face_map: list[int | None],
          presentation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add the PMI of ``document`` to ``doc``, on ``part`` (a ``geometry.Part``). ``face_map``
    gives the OCCT face (index in the part's map of faces) of each haecceity face index.

    Returns ``{"unmapped": [...], "added": {kind: count}}``."""
    return _Builder(doc, part, document, face_map, presentation).run()


class _Builder:
    def __init__(self, doc, part, document, face_map, presentation):
        self.doc, self.topology = doc, part
        # The part's own label: its material, attributes and notes of the whole part.
        self.part = part.home
        self.pmi = document["pmi"]
        self.units = _Units(document["units"])
        self.units.document = document["units"]
        self.shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        self.dimtol = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
        self.face_map = face_map
        self.features = {f["id"]: f["value"] for f in self.pmi["features"]}
        self.presentation = presentation
        self.unmapped: list[str] = []
        self.added: dict[str, int] = {}
        self.sub_labels: dict[tuple[str, int], Any] = {}
        self.labels: dict[str, Any] = {}  # an item's id to its XCAF label
        self.datum_faces: dict[str, list] = {}  # a datum's id to the labels of its feature's faces
        self.shown: set[str] = set()  # items whose callouts were carried
        self.current: tuple[str, dict] | None = None  # the item being built: (its group, it)
        self.lossy: dict[str, tuple[str, dict]] = {}
        self.note_labels: dict[str, Any] = {}  # items the document cannot hold in full, by id

    def run(self) -> dict[str, Any]:
        self.datums()
        self.dimensions()
        self.tolerances()
        self.notes()
        self.attributes()
        self.material()
        self.not_carried()
        self.keep()
        if self.presentation is not None:
            left = [i for i in self.presentation["items"] if i not in self.shown]
            if left:
                self.lose(f"{len(left)} items' callouts: XCAF holds callouts only on datums, "
                                     f"dimensions and tolerances ({', '.join(sorted(left)[:3])}{', …' if len(left) > 3 else ''})")
        return {"unmapped": self.unmapped, "added": self.added}

    def lose(self, line: str) -> None:
        """Something the document cannot hold: listed, and the item it belongs to kept whole."""
        self.unmapped.append(line)
        if self.current is not None:
            self.lossy.setdefault(self.current[1]["id"], self.current)

    def count(self, kind: str) -> None:
        self.added[kind] = self.added.get(kind, 0) + 1

    # Faces --------------------------------------------------------------------------------------

    def sub_label(self, kind: str, index: int):
        """The label of the part's face or edge ``index`` (OCCT's 0-based index in its map), made
        a sub-shape of the shape it lies in."""
        key = (kind, index)
        if key not in self.sub_labels:
            owner, shape, _ = (self.topology.faces if kind == "face" else self.topology.edges)[index]
            from OCP.TDF import TDF_Label
            label = TDF_Label()
            if not self.shapes.FindSubShape(owner, shape, label):
                label = self.shapes.AddSubShape(owner, shape)
            self.sub_labels[key] = label
        return self.sub_labels[key]

    def anchors(self, feature: str, seen: frozenset = frozenset()) -> tuple[list[tuple[str, int]], list[str]]:
        """The faces and edges (OCCT's indices) a feature is on, and what of it could not be placed."""
        value = self.features.get(feature)
        if value is None or feature in seen:
            return [], [f"feature {feature} unknown"]
        seen = seen | {feature}
        out, missing = [], []
        if "items" in value:
            for item in value["items"]:
                if "face" in item:
                    face = item["face"]
                    occt = self.face_map[face] if isinstance(face, int) and face < len(self.face_map) else None
                    if occt is None or self.topology.faces[occt][0] is None:
                        missing.append(f"face {face} not found in OCCT's reading")
                    else:
                        out.append(("face", occt))
                elif "edge" in item:
                    if item["edge"] < len(self.topology.edges) and self.topology.edges[item["edge"]][0] is not None:
                        out.append(("edge", item["edge"]))
                    else:
                        missing.append(f"edge {item['edge']} not found")
                else:
                    missing.append(f"geometry {item['geometry']} is not part of the shape")
        else:
            members = value["group"]["members"] if "group" in value else value["derived"]["from"]
            for member in members:
                more, gone = self.anchors(member, seen)
                out.extend(more)
                missing.extend(gone)
        return list(dict.fromkeys(out)), missing

    def on(self, feature: str | None, what: str) -> list:
        """The labels of a feature's faces and edges. What of it cannot be placed on the part (an
        item of supplemental geometry, a face OCCT did not make) is listed in ``unmapped``; an item
        placed nowhere is kept, unanchored."""
        if feature is None:
            return []
        found, missing = self.anchors(feature)
        for line in missing:
            self.lose(f"{what}: {line}" + ("; kept unanchored" if not found else ""))
        if not found and not missing:
            self.lose(f"{what}: feature {feature} has no faces; kept unanchored")
        return [self.sub_label(kind, i) for kind, i in found]

    def is_group(self, feature: str, kind: str) -> bool:
        value = self.features.get(feature, {})
        return "group" in value and value["group"]["kind"] == kind

    # Presentation -------------------------------------------------------------------------------

    def present(self, obj, id: str) -> None:
        """The item's callouts, as XCAF's presentation shape and plane of the object."""
        if self.presentation is None or id not in self.presentation["items"]:
            return
        callouts = self.presentation["items"][id]
        factor = MM.get(self.presentation.get("length_unit") or "millimetre", 1.0)
        point = lambda p: gp_Pnt(*(c * factor for c in p))
        builder, compound = BRep_Builder(), TopoDS_Compound()
        builder.MakeCompound(compound)
        empty = True
        for callout in callouts:
            for line in callout["polylines"]:
                polygon = BRepBuilderAPI_MakePolygon()
                for p in line:
                    polygon.Add(point(p))
                if polygon.IsDone():
                    builder.Add(compound, polygon.Wire())
                    empty = False
            for triangle in callout["triangles"]:
                polygon = BRepBuilderAPI_MakePolygon(*(point(p) for p in triangle), True)
                if polygon.IsDone():
                    face = BRepBuilderAPI_MakeFace(polygon.Wire(), True)
                    if face.IsDone():
                        builder.Add(compound, face.Face())
                        empty = False
        planes = {p["id"]: p for p in self.presentation.get("planes", [])}
        plane = next((planes[c["plane_id"]] for c in callouts if c.get("plane_id") in planes), None)
        if plane is not None:
            obj.SetPlane(gp_Ax2(point(plane["origin"]), gp_Dir(*plane["normal"]), gp_Dir(*plane["x_axis"])))
        if not empty:
            obj.SetPresentation(compound, _text(callouts[0]["name"]))
        self.shown.add(id)

    # Datums -------------------------------------------------------------------------------------

    def datum(self, letter: str, faces: list, what: str, modifiers=(), position: int = 0, present: str | None = None):
        label = self.dimtol.AddDatum()
        obj = XCAFDimTolObjects_DatumObject()
        obj.SetName(_text(letter))
        if position:
            obj.SetPosition(position)
        for modifier in modifiers:
            if "simple" in modifier:
                name = _DATUM_MODIFIER.get(modifier["simple"])
                if name is None:
                    self.lose(f"{what}: datum modifier {modifier['simple']} has no XCAF form")
                else:
                    obj.AddModifier(_enum(DatumSingleModif, "XCAFDimTolObjects_DatumSingleModif", name))
            else:
                kind, value = modifier["with_value"]["kind"], self.units.value(modifier["with_value"]["value"])
                obj.SetModifierWithValue(_enum(DatumModifWithValue, "XCAFDimTolObjects_DatumModifWithValue",
                                               _DATUM_MODIFIER_WITH_VALUE[kind]), value or 0.0)
        if present:
            self.present(obj, present)
        XCAFDoc_Datum.Set_s(label).SetObject(obj)
        if faces:
            self.dimtol.SetDatum(_seq(faces), label)
        return label

    def datums(self) -> None:
        targets = {t["id"]: t["value"] for t in self.pmi["datum_targets"]}
        for item in self.pmi["datums"]:
            self.current = ("datums", item)
            d, what = item["value"], f"datum {item['value']['label']}"
            faces = self.on(d["feature"], what)
            first = None
            if d["feature"] is not None or not d["targets"]:
                first = self.datum(d["label"], faces, what, present=item["id"])
                self.count("datum")
            self.datum_faces[item["id"]] = faces
            for target_id in d["targets"]:
                self.current = ("datum_targets", {"id": target_id, "value": targets[target_id]})
                label = self.target(d["label"], target_id, targets[target_id], f"{what} target {target_id}")
                self.current = ("datums", item)
                if label is not None:
                    first = first or label
                    self.labels[target_id] = label
            if first is None:
                self.lose(f"{what}: none of its targets has an XCAF form")
                continue
            self.labels[item["id"]] = first

    def target(self, letter: str, id: str, t: dict[str, Any], what: str):
        shape = t["shape"]
        kind = shape if isinstance(shape, str) else next(iter(shape))
        if kind not in ("point", "line", "rectangle", "circle", "area"):
            self.lose(f"{what}: {kind} target has no XCAF form")
            return None
        on = t["on"] if kind != "area" else shape["area"]
        faces = []
        if on:
            # A target placed by supplemental geometry alone (an isolated point) is held by its
            # placement; only faces it is on are kept as its datum's faces.
            found, missing = self.anchors(on)
            for line in missing:
                if not line.startswith("geometry "):
                    self.lose(f"{what}: {line}")
            faces = [self.sub_label(k, i) for k, i in found]
            if kind == "area" and not faces:
                self.lose(f"{what}: its area has no faces")
                return None
        label = self.dimtol.AddDatum()
        obj = XCAFDimTolObjects_DatumObject()
        obj.SetName(_text(letter))
        obj.IsDatumTarget(True)
        obj.SetDatumTargetType(_enum(DatumTargetType, "XCAFDimTolObjects_DatumTargetType", kind.capitalize()))
        obj.SetDatumTargetNumber(t["number"])
        if t["placement"] is not None:
            p = t["placement"]
            origin = [self.units.length_of(c) or 0.0 for c in p["origin"]]
            axis = [float(v) for v in p["axis"]] if p["axis"] else [0.0, 0.0, 1.0]
            if p["ref_direction"]:
                obj.SetDatumTargetAxis(gp_Ax2(gp_Pnt(*origin), gp_Dir(*axis), gp_Dir(*(float(v) for v in p["ref_direction"]))))
            else:
                obj.SetDatumTargetAxis(gp_Ax2(gp_Pnt(*origin), gp_Dir(*axis)))
        # XCAF holds a circle's diameter, and a line's length, as the target's length.
        sizes = shape[kind] if isinstance(shape, dict) and kind != "area" else {}
        if "length" in sizes or "diameter" in sizes:
            obj.SetDatumTargetLength(self.units.length_of(sizes.get("length") or sizes["diameter"]) or 0.0)
        if "width" in sizes:
            obj.SetDatumTargetWidth(self.units.length_of(sizes["width"]) or 0.0)
        if t["movable"] is not None:
            self.lose(f"{what}: movable direction has no XCAF form")
        self.present(obj, id)
        XCAFDoc_Datum.Set_s(label).SetObject(obj)
        if faces:
            self.dimtol.SetDatum(_seq(faces), label)
        self.count("datum target")
        return label

    # Dimensions ---------------------------------------------------------------------------------

    def dimensions(self) -> None:
        for item in self.pmi["dimensions"]:
            self.current = ("dimensions", item)
            id, d = item["id"], item["value"]
            what = f"dimension {id}"
            (form, kind), = d["kind"].items()
            name = kind["kind"] if isinstance(kind["kind"], str) else kind["kind"]["other"]
            if form == "size":
                first, second = self.on(kind["feature"], what), []
                occt = _SIZE.get(name) or ("Size_Angular" if name == "angle" else None)
            else:
                first, second = self.on(kind["from"], what), self.on(kind["to"], what)
                occt = _LOCATION.get(name) or ("Location_Angular" if name == "angle" else None)
            if occt is None:
                self.lose(f"{what}: {form} kind {name} has no XCAF form")
                continue
            obj = XCAFDimTolObjects_DimensionObject()
            obj.SetType(_enum(DimensionType, "XCAFDimTolObjects_DimensionType", occt))
            obj.SetSemanticName(_text(id))
            nominal = self.units.value(d["nominal"])
            if nominal is not None:
                obj.SetValue(nominal)
            if kind.get("angle"):
                obj.SetAngularQualifier(_enum(AngularQualifier, "XCAFDimTolObjects_AngularQualifier", _ANGLE[kind["angle"]]))
            if kind.get("path"):
                self.lose(f"{what}: its path has no XCAF form here")
            if kind.get("directed"):
                self.lose(f"{what}: its direction has no XCAF form here")
            self.dimension_tolerance(obj, d["tolerance"], nominal, what)
            if d["qualifier"] is not None:
                q = d["qualifier"]
                if isinstance(q, str):
                    obj.SetQualifier(_enum(DimensionQualifier, "XCAFDimTolObjects_DimensionQualifier", _QUALIFIER[q]))
                else:
                    self.lose(f"{what}: qualifier {q['other']} has no XCAF form")
            modifiers = Sequence_XCAFDimTolObjects_DimensionModif()
            for m in d["modifiers"]:
                if m in _DIMENSION_MODIFIER:
                    modifiers.Append(_enum(DimensionModif, "XCAFDimTolObjects_DimensionModif", _DIMENSION_MODIFIER[m]))
                else:
                    self.lose(f"{what}: modifier {m} has no XCAF form")
            if modifiers.Length():
                obj.SetModifiers(modifiers)
            if d["principle"] is not None:
                self.lose(f"{what}: {d['principle']} has no XCAF form")
            self.present(obj, id)
            label = self.dimtol.AddDimension()
            XCAFDoc_Dimension.Set_s(label).SetObject(obj)
            if first or second:
                self.dimtol.SetDimension(_seq(first), _seq(second), label)
            self.labels[id] = label
            self.datum_faces[id] = first
            self.count("dimension")

    def dimension_tolerance(self, obj, tolerance, nominal: float | None, what: str) -> None:
        if tolerance == "basic":
            # AP242's mark of a basic (theoretically exact) dimension, as ``read`` takes it.
            obj.AddDescription(_text("theoretical"), _text("dimensional note"))
            return
        if tolerance == "none":
            return
        (form, value), = tolerance.items()
        if form == "deviations":
            upper, lower = self.units.value(value["upper"]), self.units.value(value["lower"])
            obj.SetUpperTolValue(upper)
            # XCAF holds the lower deviation as its size below nominal.
            obj.SetLowerTolValue(-lower + 0.0)
        elif form == "limits":
            obj.SetLowerBound(self.units.value(value["lower"]))
            obj.SetUpperBound(self.units.value(value["upper"]))
        else:
            c = value["class"]
            letter = c["deviation"]["letter"]
            # XCAF names the deviation in capitals for a hole and a shaft alike, with a hole flag.
            variance = getattr(FormVariance, f"XCAFDimTolObjects_DimensionFormVariance_{letter.upper()}", None)
            grade = getattr(Grade, f"XCAFDimTolObjects_DimensionGrade_IT{c['grade']}", None)
            if variance is None or grade is None:
                self.lose(f"{what}: fit {letter}{c['grade']} has no XCAF form")
            else:
                obj.SetClassOfTolerance(c["deviation"]["of"] == "hole", variance, grade)
            if value["limits"] is not None and nominal is not None:
                upper, lower = self.units.value(value["limits"]["upper"]), self.units.value(value["limits"]["lower"])
                obj.SetUpperTolValue(float(Decimal(repr(upper)) - Decimal(repr(nominal))))
                obj.SetLowerTolValue(float(Decimal(repr(nominal)) - Decimal(repr(lower))))

    # Tolerances ---------------------------------------------------------------------------------

    def tolerances(self) -> None:
        for item in self.pmi["tolerances"]:
            self.current = ("tolerances", item)
            id, t = item["id"], item["value"]
            what = f"tolerance {id}"
            if t["kind"] not in _TOLERANCE:
                self.lose(f"{what}: {t['kind']} has no XCAF form")
                continue
            target = t["target"]
            obj = XCAFDimTolObjects_GeomToleranceObject()
            if target == "whole_part":
                faces = [self.part]
            elif "feature" in target:
                faces = self.on(target["feature"], what)
                if self.is_group(target["feature"], "all_around_shape_aspect"):
                    obj.AddModifier(GeomToleranceModif.XCAFDimTolObjects_GeomToleranceModif_All_Around)
            elif "dimension" in target:
                faces = self.datum_faces.get(target["dimension"])
                if faces is None:
                    self.lose(f"{what}: on dimension {target['dimension']}, not carried; kept unanchored")
                    faces = []
            else:
                faces = [label for f in (target["relation"]["relating"], target["relation"]["related"])
                         for label in self.on(f, what)]
            obj.SetType(_enum(GeomToleranceType, "XCAFDimTolObjects_GeomToleranceType", _TOLERANCE[t["kind"]]))
            obj.SetSemanticName(_text(id))
            magnitude = self.units.value(t["magnitude"])
            if magnitude is not None:
                obj.SetValue(magnitude)
            self.zone(obj, t["zone"], what)
            for m in t["modifiers"]:
                if m in _MATERIAL:
                    obj.SetMaterialRequirementModifier(_enum(MatReqModif, "XCAFDimTolObjects_GeomToleranceMatReqModif", _MATERIAL[m]))
                elif m in _TOLERANCE_MODIFIER:
                    obj.AddModifier(_enum(GeomToleranceModif, "XCAFDimTolObjects_GeomToleranceModif", _TOLERANCE_MODIFIER[m]))
                else:
                    self.lose(f"{what}: modifier {m} has no XCAF form")
            for a in t["auxiliary"]:
                if a == "all_over":
                    obj.AddModifier(GeomToleranceModif.XCAFDimTolObjects_GeomToleranceModif_All_Over)
                else:
                    self.lose(f"{what}: {a} has no XCAF form")
            if t["maximum"] is not None:
                obj.SetMaxValueModifier(self.units.value(t["maximum"]))
            for key, words in (("unequal", "unequally disposed zone"), ("unit_basis", "unit basis"),
                               ("description", "description")):
                if t[key] is not None:
                    self.lose(f"{what}: its {words} has no XCAF form")
            self.present(obj, id)
            label = self.dimtol.AddGeomTolerance()
            XCAFDoc_GeomTolerance.Set_s(label).SetObject(obj)
            if faces:
                self.dimtol.SetGeomTolerance(_seq(faces), label)
            self.datum_system(label, t["datums"] or [], what)
            self.labels[id] = label
            self.count("tolerance")

    def zone(self, obj, zone, what: str) -> None:
        if zone is None:
            return
        form = zone["form"] if isinstance(zone["form"], str) else None
        if form in _DIAMETER:
            obj.SetTypeOfValue(_enum(TypeValue, "XCAFDimTolObjects_GeomToleranceTypeValue", _DIAMETER[form]))
        if zone["projected"] is not None:
            obj.SetZoneModifier(ZoneModif.XCAFDimTolObjects_GeomToleranceZoneModif_Projected)
            obj.SetValueOfZoneModifier(self.units.value(zone["projected"]["length"]) or 0.0)
        elif zone["runout_angle"] is not None:
            obj.SetZoneModifier(ZoneModif.XCAFDimTolObjects_GeomToleranceZoneModif_Runout)
            obj.SetValueOfZoneModifier(self.units.value(zone["runout_angle"]) or 0.0)
        elif zone["non_uniform"] is not None:
            obj.SetZoneModifier(ZoneModif.XCAFDimTolObjects_GeomToleranceZoneModif_NonUniform)
        if zone["affected_plane"] is not None:
            self.lose(f"{what}: its affected plane has no XCAF form here")

    def datum_system(self, tolerance, compartments: list[dict[str, Any]], what: str) -> None:
        letters = {d["id"]: d["value"]["label"] for d in self.pmi["datums"]}
        plain = all(len(c["references"]) == 1 and not c["modifiers"] and not c["references"][0]["modifiers"]
                    for c in compartments)
        for position, c in enumerate(compartments, 1):
            for ref in c["references"]:
                datum = ref["datum"]
                if datum not in self.labels:
                    self.lose(f"{what}: datum {letters.get(datum, datum)} not carried")
                    continue
                if plain:
                    label = self.labels[datum]
                else:
                    label = self.datum(letters[datum], self.datum_faces.get(datum, []), what,
                                       modifiers=[*ref["modifiers"], *c["modifiers"]], position=position)
                self.dimtol.SetDatumToGeomTol(label, tolerance)

    # Notes, attributes, material ----------------------------------------------------------------

    def notes(self) -> None:
        notes = XCAFDoc_DocumentTool.NotesTool_s(self.doc.Main())
        for item in self.pmi["notes"]:
            self.current = ("notes", item)
            n, what = item["value"], f"note {item['id']}"
            on = n["on"]
            note = notes.CreateComment(TCollection_ExtendedString("haecceity"), TCollection_ExtendedString(""),
                                       TCollection_ExtendedString(n["text"], True)).Label()
            TDataStd_Name.Set_s(note, TCollection_ExtendedString(item["id"], True))
            self.note_labels[item["id"]] = note
            self.count("note")
            if on is None:
                notes.AddNote(note, self.part)
            elif "feature" in on:
                found, missing = self.anchors(on["feature"])
                for line in missing:
                    self.lose(f"{what}: {line}")
                # A note is on a face by the face's index in its shape's map of faces (1-based).
                for kind, index in found:
                    if kind == "face":
                        owner, _, at = self.topology.faces[index]
                        notes.AddNoteToSubshape(note, owner, at + 1)
                    else:
                        self.lose(f"{what}: on an edge, which XCAF's notes cannot name")
            else:
                (kind, owner), = on.items()
                if owner in self.labels:
                    notes.AddNote(note, self.labels[owner])
                else:
                    self.lose(f"{what}: on {kind} {owner}, not carried; kept on the part")
                    notes.AddNote(note, self.part)

    def attributes(self) -> None:
        """User-defined attributes, as OCCT's reader keeps them: named values on the part's label,
        a face's label or a GD&T item's label."""
        for item in self.pmi["attributes"]:
            # XCAF's named data does not read back as attributes: each is kept whole too.
            self.current = ("attributes", item)
            self.lossy[item["id"]] = self.current
            a, what = item["value"], f"attribute {item['id']}"
            on = a["on"]
            if on is None:
                labels = [self.part]
            elif "feature" in on:
                labels = self.on(on["feature"], what)
            else:
                (kind, owner), = on.items()
                labels = [self.labels[owner]] if owner in self.labels else []
            if not labels:
                self.lose(f"{what}: what it is on was not carried")
                continue
            for label in labels:
                data = self.named_data(label)
                for key, value in a["items"]:
                    self.attribute(data, " ".join(filter(None, (a["name"], key))) or item["id"], value, what)
            self.count("attribute")

    def named_data(self, label):
        from OCP.TDataStd import TDataStd_NamedData
        if XCAFDoc_ShapeTool.IsShape_s(label):
            return self.shapes.GetNamedProperties(label, True)
        return TDataStd_NamedData.Set_s(label)

    def attribute(self, data, key: str, value: dict[str, Any], what: str) -> None:
        name = TCollection_ExtendedString(key, True)
        (kind, held), = value.items()
        if kind == "text":
            data.SetString(name, TCollection_ExtendedString(held, True))
        elif kind in ("integer", "boolean"):
            data.SetInteger(name, int(held))
        elif kind == "real":
            data.SetReal(name, float(held))
        elif kind == "measure":
            data.SetReal(name, self.units.value(held) or 0.0)
        else:
            data.SetReal(name, float(held["value"]))

    def material(self) -> None:
        m = self.pmi["material"]
        self.current = None
        if m is None:
            return
        density = None if m["density"] is None else self.units.grams_per_cm3(m["density"])
        if m["density"] is not None and density is None:
            self.lose(f"material {m['id']}: its density's unit has no conversion to g/cm³")
            self.lossy["material"] = ("material", m)
        tool = XCAFDoc_DocumentTool.MaterialTool_s(self.doc.Main())
        label = tool.AddMaterial(_text(m["id"]), _text(m["name"]), density or 0.0, _text("density"),
                                 _text("POSITIVE_RATIO_MEASURE"))
        tool.SetMaterial(self.part, label)
        self.count("material")

    def not_carried(self) -> None:
        self.current = None
        names = {"general": "general tolerance", "threads": "thread", "knurls": "knurl", "holes": "hole",
                 "surface_textures": "surface texture", "tolerance_relations": "tolerance relation",
                 "derived_geometry": "derived geometry", "standards": "standard"}
        for key, name in names.items():
            for i, item in enumerate(self.pmi[key]):
                label = item.get("id") or item.get("document") or str(item)
                self.lose(f"{name} {label}: XCAF's GD&T has no place for it; kept for to_step")
                self.lossy[f"{key}/{i}"] = (key, item)
        if self.pmi["decimal_places"] is not None:
            self.lossy["decimal_places"] = ("decimal_places", self.pmi["decimal_places"])

    # What XCAF cannot hold, kept for to_step ---------------------------------------------------

    def keep(self) -> None:
        """Each item the document cannot hold in full, kept whole as haecceity's JSON on its XCAF
        label (the part's for an item with none), with the features, geometry and units it refers
        to: ``reader`` reads it back and ``to_haecceity`` restores it (see ``KEPT``)."""
        if not self.lossy:
            return
        # The datums' and targets' ids to_haecceity gives them, for the references to them.
        renamed = {d["id"]: f"datum/{d['value']['label']}" for d in self.pmi["datums"]}
        targets = {t["id"]: t["value"] for t in self.pmi["datum_targets"]}
        for d in self.pmi["datums"]:
            for t in d["value"]["targets"]:
                renamed[t] = f"datum_target/{d['value']['label']}{targets[t]['number']}"
        features = {f["id"]: f for f in self.pmi["features"]}
        geometry = {g["id"]: g for g in self.pmi["geometry"]}
        by_label: dict[str, tuple[Any, list]] = {}
        for id, (group, item) in self.lossy.items():
            label = self.labels.get(item.get("id")) if isinstance(item, dict) else None
            label = label or self.note_labels.get(item.get("id") if isinstance(item, dict) else None) or self.part
            by_label.setdefault(_entry(label), (label, []))[1].append({"group": group, "item": item})
        placed = {f: self.renumbered(features[f]) for f in features}
        for label, kept in by_label.values():
            # An item on faces outside the part's own shape (in a shape OCCT made beside it) cannot
            # be restored on it: left out, and said so.
            def placeable(held):
                return all(placed[f] is not None for f in _closure(json.dumps(held), features, geometry) if f in placed)
            for held in [h for h in kept if not placeable(h)]:
                kept.remove(held)
                what = held["item"].get("id", held["group"]) if isinstance(held["item"], dict) else held["group"]
                self.unmapped.append(f"{what}: on faces outside the part's main shape; not kept for to_step")
            if not kept:
                continue
            text = json.dumps(kept)
            used = _closure(text, features, geometry)
            fragment = {"schema": KEPT_SCHEMA, "part": _entry(self.part), "units": self.units.document, "items": kept,
                        "features": [placed[f] for f in used if f in features],
                        "geometry": [geometry[g] for g in used if g in geometry]}
            text = json.dumps(_renamed(fragment, renamed), ensure_ascii=True)
            TDataStd_AsciiString.Set_s(label, KEPT, TCollection_AsciiString(text))

    def renumbered(self, feature: dict[str, Any]) -> dict[str, Any]:
        """A feature with its faces numbered as OCCT's part numbers them (as ``to_step``'s STEP
        will)."""
        value = feature["value"]
        if "items" not in value:
            return feature
        items = []
        for i in value["items"]:
            if "face" in i and isinstance(i["face"], int):
                occt = self.face_map[i["face"]] if i["face"] < len(self.face_map) else None
                owner, _, at = self.topology.faces[occt] if occt is not None else (None, None, -1)
                if owner is None or _entry(owner) != _entry(self.part):
                    return None
                items.append({"face": at})
            elif "edge" in i:
                owner, _, at = self.topology.edges[i["edge"]] if i["edge"] < len(self.topology.edges) else (None, None, -1)
                if owner is None or _entry(owner) != _entry(self.part):
                    return None
                items.append({"edge": at})
            else:
                items.append(i)
        return {"id": feature["id"], "value": {"items": items}}


KEPT_SCHEMA = "xcaf-pmi.kept/1"
# The attribute holding what a label's item could not carry: a TDataStd_AsciiString of this GUID,
# holding JSON {"schema", "units", "items": [{"group", "item"}], "features", "geometry"}.
KEPT = Standard_GUID("5b0a6c1e-3f0d-4a5e-9a5b-6d1c7e2f9a01")


def _entry(label) -> str:
    from OCP.TCollection import TCollection_AsciiString as Ascii
    from OCP.TDF import TDF_Tool
    entry = Ascii()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _closure(text: str, features: dict, geometry: dict) -> list[str]:
    """The ids of the features (and their members) and geometry named in ``text``."""
    found, todo = [], [i for i in list(features) + list(geometry) if json.dumps(i) in text]
    while todo:
        id = todo.pop()
        if id in found:
            continue
        found.append(id)
        if id in features:
            inner = json.dumps(features[id]["value"])
            todo += [i for i in list(features) + list(geometry) if i not in found and json.dumps(i) in inner]
    return found


def _renamed(value, names: dict[str, str]):
    if isinstance(value, str):
        return names.get(value, value)
    if isinstance(value, list):
        return [_renamed(v, names) for v in value]
    if isinstance(value, dict):
        return {k: _renamed(v, names) for k, v in value.items()}
    return value
