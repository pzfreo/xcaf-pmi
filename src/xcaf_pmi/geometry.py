"""A STEP's geometry read into a new XCAF document by OCCT, with its names and colours but none
of its GD&T, and that document saved as an .xbf.

haecceity numbers a part's faces (and edges) in OCCT's ``TopExp::MapShapes`` order. ``faces``
checks that numbering against the faces OCCT read, by the STEP entity of each face, and falls
back to matching the faces by entity, then by geometry, where it does not hold; ``edges`` does
the same for the edges the PMI is on. A face or edge that cannot be matched to exactly one of
OCCT's is reported and left unanchored, never guessed.
"""

from __future__ import annotations

import functools
import json
import re
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

from xcaf_pmi.reader import _entry, _labels, _name


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


# A Part 21 string ('…', a quote doubled inside) or comment (/* … */): neither holds instances.
_QUOTED = re.compile(rb"'(?:[^']|'')*'|/\*.*?\*/", re.S)


def _data(text: bytes) -> bytes:
    """A Part 21 file's DATA section, its strings emptied and its comments removed, so that
    ``#n=`` and ``;`` in them are not taken for the file's own."""
    clean = _QUOTED.sub(lambda m: b"''" if m.group(0).startswith(b"'") else b" ", text)
    start = re.search(rb"\bDATA\b[^;]*;", clean)
    if start is None:
        return b""
    end = clean.find(b"ENDSEC", start.end())
    return clean[start.end():None if end < 0 else end]


@functools.lru_cache(maxsize=4)
def _entities_of(path: str, stamp: tuple) -> tuple[list[int], dict[int, tuple[str, list[int]]]]:
    data = _data(Path(path).read_bytes())
    order, out = [], {}
    for m in re.finditer(rb"#(\d+)\s*=\s*([^;]*);", data):
        number, body = int(m.group(1)), m.group(2)
        kind = re.match(rb"\(?\s*([A-Za-z_0-9]+)", body)
        order.append(number)
        out[number] = (kind.group(1).decode().upper() if kind else "", [int(r) for r in re.findall(rb"#(\d+)", body)])
    return order, out


def entities(path: str | Path) -> tuple[list[int], dict[int, tuple[str, list[int]]]]:
    """The file's instances: their numbers (#n) in the file's order, and each one's entity type
    and the instances it refers to, in order."""
    stat = Path(path).stat()
    return _entities_of(str(Path(path).resolve()), (stat.st_mtime_ns, stat.st_size))


def read_step_faces(path: str | Path) -> tuple[TDocStd_Document, Any]:
    """``read_step`` (no GD&T), and the STEP entity number of each face and edge OCCT made: a
    function of a face or edge (as it is in its shape's own label) giving the number of its
    ``advanced_face`` or ``edge_curve``."""
    doc, reader = _read(path, False)
    ws = reader.Reader().WS()
    process, model = ws.TransferReader().TransientProcess(), ws.Model()
    from OCP.STEPConstruct import STEPConstruct

    # The model holds the file's instances in the file's order; OCP's IdentLabel and Number give
    # 0, so each instance's own number (#n) is read from the file's text in that order.
    idents = entities(path)[0]
    if len(idents) != model.NbEntities():
        return doc, lambda face: None
    numbers = {}
    for n in range(1, model.NbEntities() + 1):
        entity = model.Value(n)
        if entity.DynamicType().Name() in ("StepShape_AdvancedFace", "StepShape_EdgeCurve"):
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
    if not path.resolve().parent.is_dir():
        raise ValueError(f"saving {path}: the folder {path.resolve().parent} does not exist")
    status = XCAFApp_Application.GetApplication_s().SaveAs(doc, TCollection_ExtendedString(str(path.resolve())))
    if status != PCDM_StoreStatus.PCDM_SS_OK:
        raise RuntimeError(f"saving {path}: OCCT could not write it ({status.name})")
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


@functools.lru_cache(maxsize=4)
def _evidence_of(path: str, stamp: tuple) -> list[dict[str, Any]]:
    import quiddity

    return json.loads(quiddity.evidence(path))["face_sources"]


def face_sources(step: str | Path) -> list[dict[str, Any]]:
    """haecceity's faces of the file, in its numbering: each one's ``advanced_face`` and
    instance (``quiddity.evidence``)."""
    stat = Path(step).stat()
    return _evidence_of(str(Path(step).resolve()), (stat.st_mtime_ns, stat.st_size))


def faces(step: str | Path, part: Part, entity_of, offset: int = 0) -> dict[str, Any]:
    """How haecceity's face indices of a part map to OCCT's faces of it: ``{"method": "index" |
    "entity" | "geometry", "faces": [OCCT's face index for each of haecceity's faces, or None],
    "unmatched": [haecceity's indices with no face], "ambiguous": [(haecceity's index, [OCCT's
    faces it matches equally])]}``.

    haecceity states the STEP entity (``advanced_face``) of each face it numbers
    (``quiddity.evidence``); OCCT's reader states the entity of each face it made (``entity_of``,
    from ``read_step_faces``). "index" means every face is the one its index says. Otherwise faces
    are matched by their entity ("entity") and, where OCCT made a face of no entity haecceity
    numbers, by their geometry ("geometry", see ``_by_geometry``): one to one, each OCCT face used
    once, and a face that matches no face, or several, or one another face matches as well, left
    unanchored. ``offset`` is the part's first face in haecceity's numbering of the file."""
    sources = face_sources(step)
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
        return {"method": "index", "faces": list(range(len(ours))), "unmatched": [], "ambiguous": []}
    where = {key: i for i, key in enumerate(ours) if key[0] is not None}
    out: list[int | None] = [where.get(key) for key in theirs]
    left = [i for i, j in enumerate(out) if j is None]
    if not left:
        return {"method": "entity", "faces": out, "unmatched": [], "ambiguous": []}
    found, ambiguous = _by_geometry(step, part, offset, left, {j for j in out if j is not None})
    for i, j in found.items():
        out[i] = j
    unmatched = [i for i in left if out[i] is None and i not in dict(ambiguous)]
    return {"method": "geometry", "faces": out, "unmatched": unmatched, "ambiguous": ambiguous}


def _props(face) -> tuple[float, tuple[float, float, float]]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    c = props.CentreOfMass()
    return props.Mass(), (c.X(), c.Y(), c.Z())


def _neighbours(part: Part) -> list[int]:
    """How many other faces each of the part's faces shares an edge with, in its own shape."""
    from OCP.collections import IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as Ancestors
    from OCP.TopExp import TopExp_Explorer

    maps: dict[str, Any] = {}
    out = []
    for owner, face, _ in part.faces:
        if owner is None:
            out.append(-1)
            continue
        key = _entry(owner)
        if key not in maps:
            maps[key] = Ancestors()
            TopExp.MapShapesAndAncestors_s(XCAFDoc_ShapeTool.GetShape_s(owner), TopAbs_EDGE, TopAbs_FACE, maps[key])
        others = ShapeMap()
        explorer = TopExp_Explorer(face, TopAbs_EDGE)
        while explorer.More():
            at = maps[key].FindIndex(explorer.Current())
            if at:
                for other in maps[key].FindFromIndex(at):
                    if not other.IsSame(face):
                        others.Add(other)
            explorer.Next()
        out.append(others.Extent())
    return out


def _by_geometry(step, part: Part, offset: int, left: list[int], taken: set[int]):
    """haecceity's faces ``left`` matched to OCCT's faces not ``taken``, by their geometry: their
    area, centre and number of neighbouring faces as haecceity states them for every face at once
    (``quiddity.fingerprints``, one reading of the file), and, where that leaves more than one
    face or the match is not close, by a point haecceity places on the face
    (``quiddity.anchor``), which must lie on OCCT's. Then one to one: a face whose only match is
    one face, which no other face has as its only match, is that face, and it is no other's.

    Returns ``({haecceity's index: OCCT's index or None}, [(haecceity's index, [OCCT's faces it
    matches]) for each face left unmatched by ambiguity])``."""
    import quiddity

    try:
        prints = json.loads(quiddity.fingerprints(str(step)))["faces"]
    except Exception:  # noqa: BLE001 - without them every face is placed by its point
        prints = []
    whole = shape_map(part.shape)
    scale = max(1.0, _size(part.shape))
    free = [k for k in range(whole.Extent()) if k not in taken]
    props = {k: _props(whole.FindKey(k + 1)) for k in free}
    around = _neighbours(part)

    def close(f, k, area: float, centre: float) -> bool:
        a, c = props[k]
        if f.get("area") is not None and abs(a - f["area"]) > area * max(abs(a), 1e-12):
            return False
        return f.get("centroid") is None or sum((x - y) ** 2 for x, y in zip(c, f["centroid"])) ** 0.5 <= centre * scale

    candidates: dict[int, set[int]] = {}
    for i in left:
        f = prints[offset + i] if offset + i < len(prints) else None
        if f is None:
            near = free
        else:
            count = len({n[0] for n in f.get("neighbours", [])} - {f.get("index")})
            near = [k for k in free if around[k] == count and close(f, k, 0.25, 5e-3)]
            tight = [k for k in near if close(f, k, 1e-3, 1e-5)]
            if len(tight) == 1:
                candidates[i] = set(tight)
                continue
        if near:
            point = json.loads(quiddity.anchor(str(step), offset + i))["point"]
            near = [k for k in near if _distance(point, whole.FindKey(k + 1)) <= 1e-6 * scale]
        candidates[i] = set(near)
    found: dict[int, int | None] = {}
    changed = True
    while changed:
        changed = False
        for i, c in candidates.items():
            if i in found or len(c) != 1:
                continue
            k = next(iter(c))
            if any(j != i and j not in found and d == {k} for j, d in candidates.items()):
                continue  # another face matches it as well: neither is that face
            found[i] = k
            for j, d in candidates.items():
                if j != i:
                    d.discard(k)
            changed = True
    ambiguous = [(i, sorted(candidates[i])) for i in left if i not in found and candidates[i]]
    return {i: found.get(i) for i in left}, ambiguous


def edges(step: str | Path, part: Part, entity_of, used, face_map: list[int | None], offset: int = 0) -> dict[str, Any]:
    """How haecceity's edge indices ``used`` (those its PMI is on) map to OCCT's edges of the part:
    ``{"method": "index" | "entity" | "geometry", "edges": {haecceity's index: OCCT's index or
    None}, "unmatched": [(haecceity's index, why)]}``.

    quiddity 0.4 states no entity for an edge, so each of haecceity's edges is taken to be the
    ``edge_curve`` its numbering gives (the file's edges, face by face in haecceity's order of
    faces, loop by loop) only where the STEP's PMI is on that edge (a
    ``geometric_item_specific_usage`` of it): where haecceity's numbering has edges the file has
    not, that check fails and the edge is reported. "index" means OCCT's edge of that index is that
    entity. Otherwise the edge is OCCT's of that entity ("entity") or, where OCCT made no edge of
    it, the one edge OCCT's faces of the entity's faces share ("geometry"). One to one: each OCCT
    edge is one haecceity edge's."""
    usage = pmi_edges(step)
    numbered, on_faces = edge_numbering(step, offset, len(part.faces))
    ours = [None if edge is None else entity_of(edge) for _, edge, _ in part.edges]
    where: dict[int, int] = {}
    for j, entity in enumerate(ours):
        if entity is not None:
            where.setdefault(entity, j)
    out: dict[int, int | None] = {}
    unmatched: list[tuple[int, str]] = []
    method, claimed = "index", set()
    for k in sorted(set(used)):
        entity = numbered[k] if 0 <= k < len(numbered) else None
        if entity is None or entity not in usage:
            out[k] = None
            unmatched.append((k, "haecceity's numbering of it cannot be checked against the file's edges"))
            continue
        if k < len(ours) and ours[k] == entity:
            j = k
        elif entity in where:
            method, j = ("entity" if method == "index" else method), where[entity]
        else:
            method = "geometry"
            j = _shared_edge(part, [face_map[i] for i in on_faces.get(entity, []) if i < len(face_map)])
            if j is None:
                unmatched.append((k, f"OCCT made no one edge of #{entity}"))
        if j is not None and j in claimed:
            unmatched.append((k, f"OCCT's edge {j} is another edge's already"))
            j = None
        out[k] = j
        if j is not None:
            claimed.add(j)
    return {"method": method, "edges": out, "unmatched": unmatched}


def pmi_edges(step: str | Path) -> set[int]:
    """The ``edge_curve`` instances the file's PMI is on: those of its
    ``geometric_item_specific_usage`` instances."""
    held = entities(step)[1]
    return {refs[-1] for kind, refs in held.values()
            if kind == "GEOMETRIC_ITEM_SPECIFIC_USAGE" and refs and held.get(refs[-1], ("",))[0] == "EDGE_CURVE"}


def edge_numbering(step: str | Path, offset: int, count: int) -> tuple[list[int], dict[int, list[int]]]:
    """The file's edges of a part (``edge_curve`` numbers) as haecceity numbers them, as far as the
    file tells: face by face in haecceity's order of the part's ``count`` faces from ``offset``,
    loop by loop, each edge once; and each edge's faces (their indices in the part). Where
    haecceity numbers an edge the file has not (OCCT's seams, say), the numbers after it differ:
    ``pmi_edges`` checks them."""
    held = entities(step)[1]
    numbered: list[int] = []
    on_faces: dict[int, list[int]] = {}
    for i, source in enumerate(face_sources(step)[offset:offset + count]):
        for bound in held.get(source["entity"], ("", []))[1]:
            if held.get(bound, ("",))[0] not in ("FACE_BOUND", "FACE_OUTER_BOUND"):
                continue
            for loop in held[bound][1]:
                for oriented in held.get(loop, ("", []))[1]:
                    if held.get(oriented, ("",))[0] != "ORIENTED_EDGE":
                        continue
                    for edge in held[oriented][1]:
                        if held.get(edge, ("",))[0] == "EDGE_CURVE":
                            if edge not in on_faces:
                                numbered.append(edge)
                            on_faces.setdefault(edge, []).append(i)
    return numbered, on_faces


def edge_print(edge) -> tuple:
    """An edge's curve, length and centre (rounded): to tell one edge from another."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopoDS import TopoDS

    edge = TopoDS.Edge(edge)
    props = GProp_GProps()
    BRepGProp.LinearProperties_s(edge, props)
    c = props.CentreOfMass()
    return (BRepAdaptor_Curve(edge).GetType().name, round(props.Mass(), 6), round(c.X(), 6), round(c.Y(), 6), round(c.Z(), 6))


def _shared_edge(part: Part, faces: list[int | None]) -> int | None:
    """The one edge of the part (its index) that OCCT's faces ``faces`` all have, if one."""
    if not faces or None in faces:
        return None
    whole_faces, whole_edges = shape_map(part.shape), shape_map(part.shape, TopAbs_EDGE)
    common = None
    for f in faces:
        mine = shape_map(whole_faces.FindKey(f + 1), TopAbs_EDGE)
        indices = {whole_edges.FindIndex(mine.FindKey(i)) - 1 for i in range(1, mine.Extent() + 1)}
        common = indices if common is None else common & indices
    common = {i for i in common if i >= 0}
    return next(iter(common)) if len(common) == 1 else None


def _size(shape) -> float:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    return 0.0 if box.IsVoid() else box.CornerMin().Distance(box.CornerMax())


def part_name(label) -> str | None:
    return _name(label)
