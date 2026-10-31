"""Map the intermediate form (``read``) to haecceity's PMI JSON, ``haecceity.pmi/1``
(quiddity-rust#142), for haecceity to write onto the STEP ``export_step`` made.

Faces are referenced by the names ``export_step`` writes on them (``{"name": ...}``), or by
index where a face has no name. One feature per reference, as haecceity's own export of a
STEP makes them. Every reference between items is an item id (the v1 contract); ids are the
producer's item names where it has them. What has no mapping yet is listed in ``unmapped``,
never guessed.

A note has one owner in ``haecceity.pmi/1``: the faces it is on (one feature of them all), or,
where it is on no face, the first dimension, tolerance or datum target it annotates. A note on a
whole part has no owner (a note of the part). What else a note is on is listed in ``unmapped``.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "haecceity.pmi/1"
MM = "unit/mm"
G_PER_CM3 = "unit/g-per-cm3"

SIZE = {
    "Size_CurveLength": "curve length", "Size_Diameter": "diameter",
    "Size_SphericalDiameter": "spherical diameter", "Size_Radius": "radius",
    "Size_SphericalRadius": "spherical radius", "Size_ToroidalMinorDiameter": "toroidal minor diameter",
    "Size_ToroidalMajorDiameter": "toroidal major diameter", "Size_ToroidalMinorRadius": "toroidal minor radius",
    "Size_ToroidalMajorRadius": "toroidal major radius",
    "Size_ToroidalHighMajorDiameter": "toroidal high major diameter",
    "Size_ToroidalLowMajorDiameter": "toroidal low major diameter",
    "Size_ToroidalHighMajorRadius": "toroidal high major radius",
    "Size_ToroidalLowMajorRadius": "toroidal low major radius", "Size_Thickness": "thickness",
}
LOCATION = {
    "Location_CurvedDistance": "curved distance", "Location_LinearDistance": "linear distance",
    "Location_LinearDistance_FromCenterToOuter": "linear distance centre outer",
    "Location_LinearDistance_FromCenterToInner": "linear distance centre inner",
    "Location_LinearDistance_FromOuterToCenter": "linear distance outer centre",
    "Location_LinearDistance_FromOuterToOuter": "linear distance outer outer",
    "Location_LinearDistance_FromOuterToInner": "linear distance outer inner",
    "Location_LinearDistance_FromInnerToCenter": "linear distance inner centre",
    "Location_LinearDistance_FromInnerToOuter": "linear distance inner outer",
    "Location_LinearDistance_FromInnerToInner": "linear distance inner inner",
}
TOLERANCE = {
    "Angularity": "angularity_tolerance", "CircularRunout": "circular_runout_tolerance",
    "Coaxiality": "coaxiality_tolerance", "Concentricity": "concentricity_tolerance",
    "Cylindricity": "cylindricity_tolerance", "Flatness": "flatness_tolerance",
    "ProfileOfLine": "line_profile_tolerance", "Parallelism": "parallelism_tolerance",
    "Perpendicularity": "perpendicularity_tolerance", "Position": "position_tolerance",
    "Roundness": "roundness_tolerance", "Straightness": "straightness_tolerance",
    "ProfileOfSurface": "surface_profile_tolerance", "Symmetry": "symmetry_tolerance",
    "TotalRunout": "total_runout_tolerance",
}
TARGET = {"Point": "point", "Line": "line", "Rectangle": "rectangle", "Circle": "circle"}
ZONE = {"None": None, "Diameter": "cylindrical or circular", "SphericalDiameter": "spherical"}
MATERIAL = {"None": None, "M": "maximum_material_requirement", "L": "least_material_requirement"}


def _decimal(value: float) -> str:
    return repr(float(value) + 0.0).replace("inf", "0")


def _mm(value: float) -> dict[str, Any]:
    return {"unit": MM, "value": _decimal(value)}


def _length(value: float) -> dict[str, Any]:
    return {"decimal_places": None, "quantity": {"length": _mm(value)}}


def _ids(items: list[dict[str, Any]]) -> dict[str, str]:
    """Each item's id: its name where no other item of its kind has it, else its entry (OCCT
    names every unnamed dimension "DGT:Dimension" and every unnamed tolerance "DGT:Tolerance")."""
    names = [item.get("name") for item in items]
    return {item["id"]: item["name"] if item.get("name") and names.count(item["name"]) == 1 else item["id"]
            for item in items}


def _fit(d: dict[str, Any]) -> dict[str, Any]:
    """ISO 286's class (H7), with the limits a ± tolerance beside it gives (10 H7 +0.015/0:
    10.015 and 10), summed in decimal so that they read as written."""
    from decimal import Decimal

    fit = d["fit"]
    limits = None
    if "tolerance" in d:
        at = lambda deviation: _length(float(Decimal(repr(d["value"])) + Decimal(repr(deviation))))
        limits = {"lower": at(d["tolerance"]["lower"]), "upper": at(d["tolerance"]["upper"])}
    return {"fit": {"class": {"deviation": {"letter": fit["letter"].lower(), "of": "hole" if fit["hole"] else "shaft"},
                              "grade": fit["grade"].removeprefix("IT")}, "limits": limits}}


def to_haecceity(found: dict[str, Any], part: int = 0) -> dict[str, Any]:
    """``haecceity.pmi/1`` for one part of ``read``'s result, and what could not be mapped."""
    unmapped: list[str] = list(found["unread"])
    faces = found["parts"][part]["faces"]
    names = [f.get("name") for f in faces]
    features: list[dict[str, Any]] = []

    def anchor(ref: dict[str, Any]) -> dict[str, Any]:
        name = ref.get("name")
        # A name the exported STEP gives one face only resolves there; otherwise the index.
        face = {"name": name} if name and names.count(name) == 1 else ref["face"]
        return {"face": face}

    def feature(refs: list[dict[str, Any]], what: str) -> str | None:
        if not refs or any("unresolved" in r or r.get("part") != part for r in refs):
            unmapped.append(f"{what}: faces not resolved on part {part}")
            return None
        id = f"feature/{len(features)}"
        features.append({"id": id, "value": {"items": [anchor(r) for r in refs]}})
        return id

    ids = _ids(found["dimensions"]) | _ids(found["tolerances"]) | _ids(found.get("notes", []))
    owners: dict[str, tuple[str, str]] = {}  # a mapped item's kind and id, by its entry: a note's owner

    def target(d: dict[str, Any], what: str) -> str | None:
        t = d["target"]
        if t["type"] not in TARGET:
            unmapped.append(f"{what}: {t['type'].lower()} target not mapped yet")
            return None
        if "origin" not in t:
            unmapped.append(f"{what}: no target parameters")
            return None
        on = feature(d["faces"], what) if d["faces"] else None
        if d["faces"] and on is None:
            return None
        shape = {"Point": lambda: "point", "Line": lambda: {"line": {"length": _mm(t["length"])}},
                 "Rectangle": lambda: {"rectangle": {"length": _mm(t["length"]), "width": _mm(t["width"])}},
                 # XCAF holds a circle's diameter as its length, as OCCT's STEP reader and writer do.
                 "Circle": lambda: {"circle": {"diameter": _mm(t["length"])}}}[t["type"]]()
        id = f"datum_target/{d['name']}{t['number']}"
        datum_targets.append({"id": id, "value": {
            "number": t["number"], "shape": shape, "movable": None, "on": on,
            "placement": {"origin": [_mm(v) for v in t["origin"]], "axis": [_decimal(v) for v in t["axis"]],
                          "ref_direction": [_decimal(v) for v in t["x"]]}}})
        owners[d["id"]] = ("datum_target", id)
        return id

    # OCCT keeps each target of a datum as a datum of the same name: one haecceity datum each name,
    # on the faces of its datum that is no target (if any), with its targets.
    named: dict[str, list[dict[str, Any]]] = {}
    for d in found["datums"]:
        named.setdefault(d["name"], []).append(d)
    datums, datum_targets, letters = [], [], {}
    for name, group in named.items():
        what = f"datum {name}"
        plain = [d for d in group if d["target"] is None]
        if any(d["modifiers"] for d in group) or len(plain) > 1:
            unmapped.append(f"{what}: modifiers, or more than one datum feature, not mapped yet")
            continue
        f = feature(plain[0]["faces"], what) if plain else None
        if plain and f is None:
            continue
        targets = [id for d in group if d["target"] is not None
                   if (id := target(d, f"{what} target {d['target']['number']}")) is not None]
        if f is None and not targets:
            continue
        letters[name] = f"datum/{name}"
        datums.append({"id": letters[name], "value": {"feature": f, "label": name, "targets": targets}})

    dimensions = []
    for d in found["dimensions"]:
        what = f"dimension {d.get('name') or d['id']}"
        if d["modifiers"] or d.get("qualifier") or "range" in d:
            unmapped.append(f"{what}: modifiers, qualifier or limits not mapped yet")
            continue
        if d["type"] in SIZE and not d["to"]:
            f = feature(d["faces"], what)
            if f is None:
                continue
            kind = {"size": {"angle": None, "feature": f, "kind": SIZE[d["type"]], "path": None}}
        elif d["type"] in LOCATION and d["to"]:
            a, b = feature(d["faces"], what), feature(d["to"], what)
            if a is None or b is None:
                continue
            kind = {"location": {"angle": None, "directed": False, "from": a, "kind": LOCATION[d["type"]],
                                 "path": None, "to": b}}
        else:
            unmapped.append(f"{what}: type {d['type']} not mapped yet")
            continue
        if d["basic"]:
            tolerance: Any = "basic"
        elif "fit" in d:
            tolerance = _fit(d)
        elif "tolerance" in d:
            tolerance = {"deviations": {"lower": _length(d["tolerance"]["lower"]),
                                        "upper": _length(d["tolerance"]["upper"])}}
        else:
            tolerance = "none"
        owners[d["id"]] = ("dimension", ids[d["id"]])
        dimensions.append({"id": ids[d["id"]], "value": {
            "kind": kind, "modifiers": [], "nominal": _length(d["value"]), "principle": None,
            "qualifier": None, "tolerance": tolerance}})

    tolerances = []
    for t in found["tolerances"]:
        what = f"tolerance {t.get('name') or t['id']}"
        if t["type"] not in TOLERANCE or t["zone"] not in ZONE or t["material"] not in MATERIAL or t["modifiers"]:
            unmapped.append(f"{what}: type, zone or modifiers not mapped yet")
            continue
        # A datum's targets are each a datum of its name in OCCT: each name is one reference.
        refs = list(dict.fromkeys(t["datums"]))
        if any(letter not in letters for letter in refs):
            unmapped.append(f"{what}: names a datum not mapped")
            continue
        f = feature(t["faces"], what)
        if f is None:
            continue
        owners[t["id"]] = ("tolerance", ids[t["id"]])
        form = ZONE[t["zone"]]
        material = MATERIAL[t["material"]]
        tolerances.append({"id": ids[t["id"]], "value": {
            "auxiliary": [],
            "datums": [{"modifiers": [], "references": [{"datum": letters[x], "modifiers": []}]}
                       for x in refs] or None,
            "description": None, "kind": TOLERANCE[t["type"]], "magnitude": _length(t["value"]),
            "maximum": None, "modifiers": [material] if material else [], "target": {"feature": f},
            "unequal": None, "unit_basis": None,
            "zone": None if form is None else {"affected_plane": None, "affected_plane_kind": None, "form": form,
                                               "non_uniform": None, "projected": None, "runout_angle": None}}})

    notes = []
    for n in found.get("notes", []):
        what = f"note {n.get('name') or n['id']}"
        on, rest = None, []
        faces_on = [ref for item in n["on"] if "faces" in item for ref in item["faces"]]
        if faces_on and (f := feature(faces_on, what)) is not None:
            on = {"feature": f}
        for item in n["on"]:
            if "faces" in item:
                continue
            (kind, entry), = item.items()
            if kind == "part":
                if len(n["on"]) > 1:
                    rest.append(f"part {entry}")
            elif on is None and entry in owners:
                on = {owners[entry][0]: owners[entry][1]}
            else:
                rest.append(f"{kind} {owners[entry][1] if entry in owners else entry}")
        if rest:
            owner = "the part" if on is None else " ".join(*on.items())
            unmapped.append(f"{what}: also on {', '.join(rest)} (a note has one owner, here {owner})")
        notes.append({"id": ids[n["id"]],
                      "value": {"kind": "semantic text", "text": n["text"], "on": on, "callouts": []}})

    # The material: XCAF's density is g/cm³. OCCT's own STEP writer states that unit as gram³·cm²,
    # which readers rightly ignore; haecceity writes it as the derived unit it is.
    held = found["parts"][part].get("material")
    material = None
    if held and held["name"]:
        density = None if held["density"] is None else {"value": _decimal(held["density"]), "unit": G_PER_CM3}
        material = {"id": held["name"], "name": None, "density": density}

    pmi = {
        "standards": [], "decimal_places": None, "features": features, "datum_targets": datum_targets,
        "datums": datums, "dimensions": dimensions, "tolerances": tolerances, "tolerance_relations": [],
        "general": [], "threads": [], "knurls": [], "holes": [], "material": material, "notes": notes,
        "surface_textures": [], "attributes": [], "geometry": [], "derived_geometry": [],
    }
    densities = [{"id": G_PER_CM3, "value": [["gram", "1."], ["centimetre", "-3."]]}] if material and material["density"] else []
    units = {"length": [{"id": MM, "value": "millimetre"}], "angle": [], "density": densities, "other": []}
    document = {"schema": SCHEMA, "units": units,
                "pmi": pmi}
    return {"document": document, "unmapped": unmapped}
