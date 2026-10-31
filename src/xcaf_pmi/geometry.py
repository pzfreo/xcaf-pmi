"""A STEP's geometry read into a new XCAF document by OCCT, with its names and colours but none
of its GD&T, and that document saved as an .xbf.

haecceity numbers a part's faces (and edges) in OCCT's ``TopExp::MapShapes`` order. ``faces``
checks that numbering against the faces OCCT read, by the STEP entity of each face, and falls
back to matching the faces by entity, then by geometry, where it does not hold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as ShapeMap
from OCP.IFSelect import IFSelect_ReturnStatus
from OCP.Interface import Interface_Static
from OCP.PCDM import PCDM_StoreStatus
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
from OCP.TopExp import TopExp
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

from xcaf_pmi.reader import _labels, _name


def new_document() -> TDocStd_Document:
    """An empty XCAF document that can be saved as an .xbf."""
    app = XCAFApp_Application.GetApplication_s()
    BinXCAFDrivers.DefineFormat_s(app)
    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    app.InitDocument(doc)
    return doc


def read_step(path: str | Path, *, gdt: bool = False) -> TDocStd_Document:
    """The STEP read by OCCT's XCAF reader into a new document: shapes, names, colours and layers,
    and, only with ``gdt``, OCCT's own reading of its GD&T, material, views and attributes."""
    return _read(path, gdt)[0]


def read_step_faces(path: str | Path) -> tuple[TDocStd_Document, Any]:
    """``read_step`` (no GD&T), and the STEP entity number of each face OCCT made: a function of
    a face (as it is in its shape's own label) giving the number of its ``advanced_face``."""
    doc, reader = _read(path, False)
    ws = reader.Reader().WS()
    process, model = ws.TransferReader().TransientProcess(), ws.Model()
    from OCP.STEPConstruct import STEPConstruct

    # The model holds the file's instances in the file's order; OCP's IdentLabel and Number give
    # 0, so each instance's own number (#n) is read from the file's text in that order.
    import re
    text = Path(path).read_bytes()
    idents = [int(m) for m in re.findall(rb"#(\d+)\s*=", text[text.find(b"DATA;"):])]
    if len(idents) != model.NbEntities():
        return doc, lambda face: None
    numbers = {}
    for n in range(1, model.NbEntities() + 1):
        entity = model.Value(n)
        if entity.DynamicType().Name() == "StepShape_AdvancedFace":
            numbers[entity] = idents[n - 1]
    made, of = ShapeMap(), []
    for i in range(1, process.NbMapped() + 1):
        entity = process.Mapped(i)
        if entity in numbers:
            face = STEPConstruct.FindShape_s(process, entity)
            if not face.IsNull():
                made.Add(face)
                of.append(numbers[entity])
    return doc, lambda face: of[made.FindIndex(face) - 1] if made.FindIndex(face) else None


def _read(path, gdt: bool):
    from OCP.Message import Message, Message_Printer
    Message.DefaultMessenger_s().RemovePrinters(Message_Printer.get_type_descriptor_s())
    doc = new_document()
    reader = STEPCAFControl_Reader()
    # The reader defines the translator's parameters: set them once it exists.
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    reader.SetLayerMode(True)
    reader.SetPropsMode(True)
    for mode in (reader.SetGDTMode, reader.SetMatMode, reader.SetViewMode, reader.SetMetaMode):
        mode(gdt)
    if reader.ReadFile(str(path)) != IFSelect_ReturnStatus.IFSelect_RetDone:
        raise ValueError(f"{path}: OCCT cannot read it as STEP")
    if not reader.Transfer(doc):
        raise RuntimeError(f"{path}: OCCT could not transfer the STEP")
    return doc, reader


def save(doc: TDocStd_Document, path: str | Path) -> Path:
    """The document saved as an .xbf (BinXCAF)."""
    path = Path(path)
    if path.suffix.lower() != ".xbf":
        raise ValueError(f"{path.name}: give an .xbf path")
    status = XCAFApp_Application.GetApplication_s().SaveAs(doc, TCollection_ExtendedString(str(path.resolve())))
    if status != PCDM_StoreStatus.PCDM_SS_OK:
        raise RuntimeError(f"saving {path}: {status.name}")
    return path


def shapes(doc: TDocStd_Document) -> list[Any]:
    """The labels of the document's top-level shapes that have faces, in the document's order:
    its parts, and the assemblies OCCT makes of a part whose shape has several items (a solid
    and some surfaces, say), which haecceity takes as one part."""
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    return [label for label in _labels(tool.GetShapes) if shape_map(XCAFDoc_ShapeTool.GetShape_s(label)).Extent()]


def shape_map(shape, kind=TopAbs_FACE) -> ShapeMap:
    found = ShapeMap()
    TopExp.MapShapes_s(shape, kind, found)
    return found


def _leaves(label, location=None):
    """The shapes (not assemblies) a label is made of, each with its label and its placement in
    the label's shape, in the order of the label's components."""
    from OCP.TDF import TDF_Label

    if not XCAFDoc_ShapeTool.IsAssembly_s(label):
        yield label, location
        return
    for component in _labels(lambda seq: XCAFDoc_ShapeTool.GetComponents_s(label, seq, False)):
        referred = TDF_Label()
        XCAFDoc_ShapeTool.GetReferredShape_s(component, referred)
        placed = XCAFDoc_ShapeTool.GetLocation_s(component)
        yield from _leaves(referred, placed if location is None else location.Multiplied(placed))


class Part:
    """A part as OCCT read it, by its label: its faces and edges in the order of its shape's map,
    each as the label of the shape it lies in (the part, or one of the shapes of an assembly OCCT
    made of it) and the face or edge there. GD&T refers to those shapes' own faces and edges."""

    def __init__(self, label):
        self.label = label
        self.shape = XCAFDoc_ShapeTool.GetShape_s(label)
        self.leaves = [(leaf, XCAFDoc_ShapeTool.GetShape_s(leaf), location) for leaf, location in _leaves(label)]
        # The shape that stands for the whole part (its material, its notes): the one with most faces.
        self.home = max(self.leaves, key=lambda leaf: shape_map(leaf[1]).Extent())[0]
        self.faces = self._items(TopAbs_FACE)
        self.edges = self._items(TopAbs_EDGE)

    def _items(self, kind) -> list[tuple[Any, Any, int]]:
        """Each face (or edge) of the part's shape as (its shape's label, the face there, its
        0-based index in that shape's map)."""
        whole = shape_map(self.shape, kind)
        if len(self.leaves) == 1 and self.leaves[0][2] is None:
            return [(self.label, whole.FindKey(i), i - 1) for i in range(1, whole.Extent() + 1)]
        maps = [(leaf, shape_map(shape, kind), shape_map(shape if location is None else shape.Moved(location), kind))
                for leaf, shape, location in self.leaves]
        out = []
        for i in range(1, whole.Extent() + 1):
            item = whole.FindKey(i)
            for leaf, own, placed in maps:
                at = placed.FindIndex(item)
                if at:
                    out.append((leaf, own.FindKey(at), at - 1))
                    break
            else:
                out.append((None, None, -1))
        return out


def _distance(point, face) -> float:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from OCP.gp import gp_Pnt

    return BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex(), face).Value()


def faces(step: str | Path, part: Part, entity_of, offset: int = 0) -> dict[str, Any]:
    """How haecceity's face indices of a part map to OCCT's faces of it: ``{"method": "index" |
    "entity" | "geometry", "faces": [OCCT's face index for each of haecceity's faces, or None],
    "unmatched": [haecceity's indices with no face]}``.

    haecceity states the STEP entity (``advanced_face``) of each face it numbers
    (``quiddity.evidence``); OCCT's reader states the entity of each face it made (``entity_of``,
    from ``read_step_faces``). "index" means every face is the one its index says. Otherwise faces
    are matched by their entity ("entity") and, where OCCT made a face of no entity haecceity
    numbers, by a point haecceity places on the face (``quiddity.anchor``), which must lie on
    OCCT's ("geometry"). ``offset`` is the part's first face in haecceity's numbering of the
    file."""
    import quiddity

    sources = json.loads(quiddity.evidence(str(step)))["face_sources"]
    def keyed(entities):
        """Each entity with its occurrence (a face of a part placed twice is one entity twice)."""
        seen: dict[Any, int] = {}
        out = []
        for entity in entities:
            out.append((entity, seen.get(entity, 0)))
            seen[entity] = seen.get(entity, 0) + 1
        return out

    theirs = keyed(s["entity"] for s in sources[offset:offset + len(part.faces)])
    ours = keyed(None if face is None else entity_of(face) for _, face, _ in part.faces)
    if theirs == ours:
        return {"method": "index", "faces": list(range(len(ours))), "unmatched": []}
    where = {key: i for i, key in enumerate(ours) if key[0] is not None}
    out, unmatched, method = [], [], "entity"
    scale = 1e-6 * max(1.0, _size(part.shape))
    for i, key in enumerate(theirs):
        j = where.get(key)
        if j is None:
            method = "geometry"
            point = json.loads(quiddity.anchor(str(step), offset + i))["point"]
            located = shape_map(part.shape)
            j = next((k for k in range(located.Extent()) if _distance(point, located.FindKey(k + 1)) <= scale), None)
            if j is None:
                unmatched.append(i)
        out.append(j)
    return {"method": method, "faces": out, "unmatched": unmatched}


def _size(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return 0.0 if box.IsVoid() else box.CornerMin().Distance(box.CornerMax())


def part_name(label) -> str | None:
    return _name(label)
