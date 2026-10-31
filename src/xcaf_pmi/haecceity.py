"""Map the intermediate form (``read``) to haecceity's PMI JSON, ``haecceity.pmi/1``
(quiddity-rust#142), for haecceity to write onto the STEP ``export_step`` made.

Faces are referenced by the names ``export_step`` writes on them (``{"name": ...}``), or by
index where a face has no name. One feature per reference, as haecceity's own export of a
STEP makes them. Every reference between items is an item id (the v1 contract); ids are the
producer's item names where it has them. What has no mapping yet is listed in ``unmapped``,
never guessed.
"""

from __future__ import annotations

from typing import Any

SCHEMA = "haecceity.pmi/1"
MM = "unit/mm"

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
ZONE = {"None": None, "Diameter": "cylindrical or circular", "SphericalDiameter": "spherical"}
MATERIAL = {"None": None, "M": "maximum_material_requirement", "L": "least_material_requirement"}


def _decimal(value: float) -> str:
    return repr(float(value)).replace("inf", "0")


def _length(value: float) -> dict[str, Any]:
    return {"decimal_places": None, "quantity": {"length": {"unit": MM, "value": _decimal(value)}}}


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

    datums, letters = [], {}
    for d in found["datums"]:
        if d["modifiers"] or d["target"]:
            unmapped.append(f"datum {d['name']}: modifiers or targets not mapped yet")
            continue
        f = feature(d["faces"], f"datum {d['name']}")
        if f is None:
            continue
        letters[d["name"]] = f"datum/{d['name']}"
        datums.append({"id": letters[d["name"]], "value": {"feature": f, "label": d["name"], "targets": []}})

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
        elif "tolerance" in d:
            tolerance = {"deviations": {"lower": _length(d["tolerance"]["lower"]),
                                        "upper": _length(d["tolerance"]["upper"])}}
        else:
            tolerance = "none"
        dimensions.append({"id": d.get("name") or d["id"], "value": {
            "kind": kind, "modifiers": [], "nominal": _length(d["value"]), "principle": None,
            "qualifier": None, "tolerance": tolerance}})

    tolerances = []
    for t in found["tolerances"]:
        what = f"tolerance {t.get('name') or t['id']}"
        if t["type"] not in TOLERANCE or t["zone"] not in ZONE or t["material"] not in MATERIAL or t["modifiers"]:
            unmapped.append(f"{what}: type, zone or modifiers not mapped yet")
            continue
        if any(letter not in letters for letter in t["datums"]):
            unmapped.append(f"{what}: names a datum not mapped")
            continue
        f = feature(t["faces"], what)
        if f is None:
            continue
        form = ZONE[t["zone"]]
        material = MATERIAL[t["material"]]
        tolerances.append({"id": t.get("name") or t["id"], "value": {
            "auxiliary": [],
            "datums": [{"modifiers": [], "references": [{"datum": letters[x], "modifiers": []}]}
                       for x in t["datums"]] or None,
            "description": None, "kind": TOLERANCE[t["type"]], "magnitude": _length(t["value"]),
            "maximum": None, "modifiers": [material] if material else [], "target": {"feature": f},
            "unequal": None, "unit_basis": None,
            "zone": None if form is None else {"affected_plane": None, "affected_plane_kind": None, "form": form,
                                               "non_uniform": None, "projected": None, "runout_angle": None}}})

    notes = [{"id": n.get("name") or n["id"],
              "value": {"kind": "semantic text", "text": n["text"], "on": None, "callouts": []}}
             for n in found.get("notes", [])]

    pmi = {
        "standards": [], "decimal_places": None, "features": features, "datum_targets": [],
        "datums": datums, "dimensions": dimensions, "tolerances": tolerances, "tolerance_relations": [],
        "general": [], "threads": [], "knurls": [], "holes": [], "material": None, "notes": notes,
        "surface_textures": [], "attributes": [], "geometry": [], "derived_geometry": [],
    }
    units = {"length": [{"id": MM, "value": "millimetre"}], "angle": [], "density": [], "other": []}
    document = {"schema": SCHEMA, "units": units,
                "pmi": pmi}
    return {"document": document, "unmapped": unmapped}
