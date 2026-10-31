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

import json
from typing import Any

SCHEMA = "haecceity.pmi/1"
MM = "unit/mm"
DEGREE = "unit/degree"
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
# OCCT's names (its enumerations' suffixes) for haecceity's tolerance modifiers that XCAF holds as
# such; all-around and all-over are haecceity's feature group and auxiliary classification.
TOLERANCE_MODIFIER = {
    "Any_Cross_Section": "any_cross_section", "Common_Zone": "common_zone",
    "Each_Radial_Element": "each_radial_element", "Free_State": "free_state", "Line_Element": "line_element",
    "Major_Diameter": "major_diameter", "Minor_Diameter": "minor_diameter", "Not_Convex": "not_convex",
    "Pitch_Diameter": "pitch_diameter", "Reciprocity_Requirement": "reciprocity_requirement",
    "Separate_Requirement": "separate_requirement", "Statistical_Tolerance": "statistical_tolerance",
    "Tangent_Plane": "tangent_plane",
}
DIMENSION_MODIFIER = {
    "ControlledRadius": "controlled radius", "Square": "square", "StatisticalTolerance": "statistical",
    "ContinuousFeature": "continuous feature", "TwoPointSize": "two point size",
    "LocalSizeDefinedBySphere": "local size defined by a sphere",
    "LeastSquaresAssociationCriterion": "least squares association criteria",
    "MaximumInscribedAssociation": "maximum inscribed association criteria",
    "MinimumCircumscribedAssociation": "minimum circumscribed association criteria",
    "CircumferenceDiameter": "circumference diameter calculated size", "AreaDiameter": "area diameter calculated size",
    "VolumeDiameter": "volume diameter calculated size", "MaximumSize": "maximum rank order size",
    "MinimumSize": "minimum rank order size", "AverageSize": "average rank order size",
    "MedianSize": "median rank order size", "MidRangeSize": "mid range rank order size",
    "RangeOfSizes": "range rank order size", "AnyRestrictedPortionOfFeature": "any part of the feature",
    "AnyCrossSection": "any cross section", "SpecificFixedCrossSection": "specific fixed cross section",
    "CommonTolerance": "common tolerance", "FreeStateCondition": "free state condition",
}
DATUM_MODIFIER = {
    "AnyCrossSection": "any_cross_section", "Any_LongitudinalSection": "any_longitudinal_section",
    "Basic": "basic", "ContactingFeature": "contacting_feature",
    "DegreeOfFreedomConstraintU": "degree_of_freedom_constraint_u",
    "DegreeOfFreedomConstraintV": "degree_of_freedom_constraint_v",
    "DegreeOfFreedomConstraintW": "degree_of_freedom_constraint_w",
    "DegreeOfFreedomConstraintX": "degree_of_freedom_constraint_x",
    "DegreeOfFreedomConstraintY": "degree_of_freedom_constraint_y",
    "DegreeOfFreedomConstraintZ": "degree_of_freedom_constraint_z", "DistanceVariable": "distance_variable",
    "FreeState": "free_state", "LeastMaterialRequirement": "least_material_requirement", "Line": "line",
    "MajorDiameter": "major_diameter", "MaximumMaterialRequirement": "maximum_material_requirement",
    "MinorDiameter": "minor_diameter", "Orientation": "orientation", "PitchDiameter": "pitch_diameter",
    "Plane": "plane", "Point": "point", "Translation": "translation",
}
DATUM_MODIFIER_WITH_VALUE = {"CircularOrCylindrical": "circular_or_cylindrical", "Distance": "distance",
                             "Projected": "projected", "Spherical": "spherical"}
QUALIFIER = {"Min": "minimum", "Max": "maximum", "Avg": "average"}
ANGLE = {"Small": "small", "Large": "large", "Equal": "equal"}


def _decimal(value: float) -> str:
    return repr(float(value) + 0.0).replace("inf", "0")


def _mm(value: float) -> dict[str, Any]:
    return {"unit": MM, "value": _decimal(value)}


def _length(value: float) -> dict[str, Any]:
    return {"decimal_places": None, "quantity": {"length": _mm(value)}}


def _angle(value: float) -> dict[str, Any]:
    return {"decimal_places": None, "quantity": {"angle": {"unit": DEGREE, "value": _decimal(value)}}}


def _suffix(enum: str, prefix: str) -> str:
    return enum.removeprefix(f"XCAFDimTolObjects_{prefix}_")


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
        if "edge" in ref:
            return {"edge": ref["edge"]}
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
        if t["type"] == "Area":
            # An area target is the area of the faces it is on.
            area = feature(d["faces"], what)
            if area is None:
                return None
            id = f"datum_target/{d['name']}{t['number']}"
            placement = None if "origin" not in t else {
                "origin": [_mm(v) for v in t["origin"]], "axis": [_decimal(v) for v in t["axis"]],
                "ref_direction": [_decimal(v) for v in t["x"]]}
            datum_targets.append({"id": id, "value": {"number": t["number"], "shape": {"area": area},
                                                       "movable": None, "on": None, "placement": placement}})
            owners[d["id"]] = ("datum_target", id)
            return id
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

    # OCCT keeps each target of a datum as a datum of the same name, and may keep a datum for each
    # tolerance referring to it (with that reference's modifiers and compartment): one haecceity
    # datum each name, on the faces of its datums that are no target (if any), with its targets.
    named: dict[str, list[dict[str, Any]]] = {}
    for d in found["datums"]:
        # Only this part's datums (on its faces, or on none).
        if all(r.get("part") == part for r in d["faces"]):
            named.setdefault(d["name"], []).append(d)
    datums, datum_targets, letters = [], [], {}
    for name, group in named.items():
        what = f"datum {name}"
        plain = [d for d in group if d["target"] is None]
        placed = list(dict.fromkeys(tuple((r.get("part"), r.get("face"), r.get("unresolved")) for r in d["faces"])
                                    for d in plain if d["faces"]))
        if len(placed) > 1:
            unmapped.append(f"{what}: more than one datum feature, not mapped yet")
            continue
        on = next(d["faces"] for d in plain if d["faces"]) if placed else None
        f = feature(on, what) if on else None
        if on and f is None:
            continue
        targets = [id for d in group if d["target"] is not None
                   if (id := target(d, f"{what} target {d['target']['number']}")) is not None]
        if f is None and not targets:
            unmapped.append(f"{what}: neither on faces nor of targets (haecceity's writer needs one)")
            continue
        letters[name] = f"datum/{name}"
        datums.append({"id": letters[name], "value": {"feature": f, "label": name, "targets": targets}})

    # What to_xcaf kept of the STEP's PMI that XCAF could not hold, on this part: restored whole.
    # Each fragment only where the document still states what it was kept for (see _checked).
    entry = found["parts"][part].get("entry")
    entries = {p.get("entry") for p in found["parts"]}
    kept = []
    for k in found.get("kept", []):
        where = f"PMI to_xcaf kept on {k.get('on')}"
        if k.get("schema") != KEPT_SCHEMA:
            unmapped.append(f"{where}: its schema {k.get('schema')!r} is not {KEPT_SCHEMA!r}; left out")
        elif k.get("part") not in entries:
            unmapped.append(f"{where}: for part {k.get('part')}, which the document does not have; left out")
        elif k["part"] == entry:
            kept.append(_checked(k, unmapped))
    restored: set[str] = set()

    def restore(groups: tuple[str, ...], into: dict[str, list]) -> None:
        for fragment in kept:
            for held in fragment["items"]:
                if held["group"] not in groups:
                    continue
                item = held["item"]
                if item["id"] in restored:
                    # Two fragments with one id (a datum renamed as to_haecceity names it, say):
                    # haecceity takes one item of an id.
                    unmapped.append(f"{held['group']} {item['id']}: kept twice by to_xcaf; the second left out")
                    continue
                group = into[held["group"]]
                at = next((i for i, x in enumerate(group) if x["id"] == item["id"]), None)
                if at is None:
                    group.append(item)
                else:
                    group[at] = item
                restored.add(item["id"])

    restore(("datums", "datum_targets"), {"datums": datums, "datum_targets": datum_targets})
    for d in datums:
        letters[d["value"]["label"]] = d["id"]

    def datum_modifiers(enums: list[str], what: str) -> list[dict[str, Any]]:
        out = []
        for e in enums:
            name = DATUM_MODIFIER.get(_suffix(e, "DatumSingleModif"))
            if name is None:
                unmapped.append(f"{what}: datum modifier {_suffix(e, 'DatumSingleModif')} not mapped yet")
            else:
                out.append({"simple": name})
        return out

    def datum_system(t: dict[str, Any], what: str) -> list[dict[str, Any]] | None:
        """The tolerance's datum system: a compartment for each position OCCT states (each datum
        in order where it states none). A compartment of one datum holds that datum's modifiers;
        a common datum (A-B) holds them on each reference."""
        refs = t.get("datum_refs") or [{"name": n, "position": 0, "modifiers": []} for n in t["datums"]]
        groups: dict[Any, list[dict[str, Any]]] = {}
        for r in refs:
            # An unpositioned datum is a compartment of its own, once for each name (OCCT keeps
            # each target of a datum as a datum of its name).
            key = r["position"] or ("name", r["name"])
            if r not in groups.setdefault(key, []):
                groups[key].append(r)
        out = []
        for group in groups.values():
            group = list({r["name"]: r for r in group}.values())
            if len(group) == 1:
                out.append({"modifiers": datum_modifiers(group[0]["modifiers"], what),
                            "references": [{"datum": letters[group[0]["name"]], "modifiers": []}]})
            else:
                out.append({"modifiers": [], "references": [
                    {"datum": letters[r["name"]], "modifiers": datum_modifiers(r["modifiers"], what)} for r in group]})
        return out or None

    dimensions = []
    for d in found["dimensions"]:
        what = f"dimension {d.get('name') or d['id']}"
        angular = d["type"] in ("Location_Angular", "Size_Angular")
        value = _angle if angular else _length
        modifiers = [DIMENSION_MODIFIER.get(_suffix(m, "DimensionModif")) for m in d["modifiers"]]
        qualifier = QUALIFIER.get(_suffix(d["qualifier"], "DimensionQualifier")) if d.get("qualifier") else None
        if None in modifiers or (d.get("qualifier") and qualifier is None):
            unmapped.append(f"{what}: modifiers or qualifier not mapped yet")
            continue
        angle = ANGLE.get(d.get("angle", ""))
        if (d["type"] in SIZE or d["type"] == "Size_Angular") and not d["to"]:
            f = feature(d["faces"], what)
            if f is None:
                continue
            kind = {"size": {"angle": angle, "feature": f, "path": None,
                             "kind": {"other": "angle"} if angular else SIZE[d["type"]]}}
        elif (d["type"] in LOCATION or d["type"] == "Location_Angular") and d["to"]:
            a, b = feature(d["faces"], what), feature(d["to"], what)
            if a is None or b is None:
                continue
            kind = {"location": {"angle": angle, "directed": False, "from": a, "path": None, "to": b,
                                 "kind": {"other": "angle"} if angular else LOCATION[d["type"]]}}
        else:
            unmapped.append(f"{what}: type {d['type']} not mapped yet")
            continue
        if d["basic"]:
            tolerance: Any = "basic"
        elif "fit" in d:
            tolerance = _fit(d)
        elif "tolerance" in d:
            tolerance = {"deviations": {"lower": value(d["tolerance"]["lower"]),
                                        "upper": value(d["tolerance"]["upper"])}}
        elif "range" in d:
            tolerance = {"limits": {"lower": value(d["range"]["lower"]), "upper": value(d["range"]["upper"])}}
        else:
            tolerance = "none"
        # XCAF has no "no value": a dimension of 0 with nothing else stated states none, which
        # AP242 does not allow (haecceity's writer refuses it).
        if d["value"] == 0 and tolerance == "none":
            unmapped.append(f"{what}: no value")
            continue
        nominal = value(d["value"])
        owners[d["id"]] = ("dimension", ids[d["id"]])
        dimensions.append({"id": ids[d["id"]], "value": {
            "kind": kind, "modifiers": modifiers, "nominal": nominal, "principle": None,
            "qualifier": qualifier, "tolerance": tolerance}})

    tolerances = []
    for t in found["tolerances"]:
        what = f"tolerance {t.get('name') or t['id']}"
        named_mods = [_suffix(m, "GeomToleranceModif") for m in t["modifiers"]]
        others = [m for m in named_mods if m not in TOLERANCE_MODIFIER and m not in ("All_Around", "All_Over")]
        zone_modifier = t.get("zone_modifier", "None")
        if t["type"] not in TOLERANCE or t["zone"] not in ZONE or t["material"] not in MATERIAL or others:
            unmapped.append(f"{what}: type, zone or modifiers not mapped yet")
            continue
        if zone_modifier not in ("None", "Projected", "Runout"):
            unmapped.append(f"{what}: {zone_modifier.lower()} zone not mapped yet")
            continue
        if zone_modifier == "Projected":
            # XCAF holds a projected zone's length but not where it ends, which AP242 requires.
            unmapped.append(f"{what}: its projected zone ({t['zone_value']!r}), whose end XCAF does not hold")
            zone_modifier = "None"
        if any(r not in letters for r in t["datums"]):
            unmapped.append(f"{what}: names a datum not mapped")
            continue
        f = feature(t["faces"], what)
        if f is None:
            continue
        if "All_Around" in named_mods:
            around = f"feature/{len(features)}"
            features.append({"id": around, "value": {"group": {"members": [f], "kind": "all_around_shape_aspect"}}})
            f = around
        owners[t["id"]] = ("tolerance", ids[t["id"]])
        form = ZONE[t["zone"]]
        material = MATERIAL[t["material"]]
        zone = None
        if form is not None or zone_modifier == "Runout":
            zone = {"affected_plane": None, "affected_plane_kind": None, "form": form or "unknown", "non_uniform": None,
                    "projected": {"end": None, "length": _length(t["zone_value"])} if zone_modifier == "Projected" else None,
                    "runout_angle": _angle(t["zone_value"]) if zone_modifier == "Runout" else None}
        tolerances.append({"id": ids[t["id"]], "value": {
            "auxiliary": ["all_over"] if "All_Over" in named_mods else [],
            "datums": datum_system(t, what),
            "description": None, "kind": TOLERANCE[t["type"]], "magnitude": _length(t["value"]),
            "maximum": _length(t["maximum"]) if t.get("maximum") else None,
            "modifiers": ([material] if material else []) + [TOLERANCE_MODIFIER[m] for m in named_mods if m in TOLERANCE_MODIFIER],
            "target": {"feature": f}, "unequal": None, "unit_basis": None, "zone": zone}})

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
        material = {"id": held["name"], "name": held.get("description"), "density": density}

    groups = {"dimensions": dimensions, "tolerances": tolerances, "notes": notes, "attributes": [],
              "general": [], "threads": [], "knurls": [], "holes": [], "surface_textures": [],
              "tolerance_relations": [], "derived_geometry": []}
    restore(tuple(groups), groups)
    standards, decimal_places, units_kept, geometry = [], None, [], []
    for fragment in kept:
        units_kept.append(fragment["units"])
        for f in fragment["features"]:
            if all(f["id"] != x["id"] for x in features):
                features.append(f)
        for g in fragment["geometry"]:
            if all(g["id"] != x["id"] for x in geometry):
                geometry.append(g)
        for held in fragment["items"]:
            if held["group"] == "standards":
                standards.append(held["item"])
            elif held["group"] == "decimal_places":
                decimal_places = held["item"]
            elif held["group"] == "material":
                material = held["item"]
    words = {"dimensions": "dimension", "tolerances": "tolerance", "notes": "note"}
    gone = {f"{words[g]} {x['id']}:" for g in words for x in groups[g] if x["id"] in restored}
    gone |= {f"datum {d['value']['label']}" for d in datums if d["id"] in restored}
    unmapped[:] = [line for line in unmapped if not any(line.startswith(g) for g in gone)]

    pmi = {
        "standards": standards, "decimal_places": decimal_places, "features": features, "datum_targets": datum_targets,
        "datums": datums, "material": material, "geometry": geometry, **groups,
    }
    densities = [{"id": G_PER_CM3, "value": [["gram", "1."], ["centimetre", "-3."]]}] if material and material["density"] else []
    angles = [{"id": DEGREE, "value": "degree"}] if '"unit/degree"' in json.dumps(pmi) else []
    units = {"length": [{"id": MM, "value": "millimetre"}], "angle": angles, "density": densities, "other": []}
    for more in units_kept:
        for kind, listed in more.items():
            units[kind] += [u for u in listed if all(u["id"] != x["id"] for x in units[kind])]
    pmi = _one_unit_each(units, pmi)
    document = {"schema": SCHEMA, "units": units,
                "pmi": pmi}
    return {"document": document, "unmapped": unmapped, "restored": sorted(restored)}


KEPT_SCHEMA = "xcaf-pmi.kept/1"


def _checked(fragment: dict[str, Any], unmapped: list[str]) -> dict[str, Any]:
    """A kept fragment with only the items the document still states as they were kept: none if
    its label's item has been edited since (its state differs; the document's own reading of it is
    used), and none that is on a face or edge, by index, that is not the one it was (its
    fingerprint differs). What is left out is said so."""
    def what(held) -> str:
        item = held["item"]
        return f"{held['group']} {item['id']}" if isinstance(item, dict) and "id" in item else held["group"]

    items = fragment.get("items") or []
    now = fragment.get("now") or {}
    if "state" not in fragment or "fingerprints" not in fragment:
        unmapped += [f"{what(h)}: kept by to_xcaf without the state to check it against; left out" for h in items]
        return {**fragment, "items": [], "features": [], "geometry": []}
    if fragment["state"] != now.get("state"):
        unmapped += [f"{what(h)}: edited in the document since to_xcaf; what XCAF cannot hold of it is left out, "
                     "and the document's own reading used" for h in items]
        return {**fragment, "items": [], "features": [], "geometry": []}
    moved = {(kind, index) for kind in ("faces", "edges")
             for index, print_ in fragment["fingerprints"].get(kind, {}).items()
             if (now.get(kind) or {}).get(index) != print_}
    if not moved:
        return fragment
    features = {f["id"]: f["value"] for f in fragment.get("features", [])}
    bad = {id for id, v in features.items()
           if any((f"{k}s", str(ref[k])) in moved for ref in v.get("items", []) for k in ("face", "edge") if k in ref)}
    grew = True
    while grew:
        more = {id for id, v in features.items() if id not in bad and any(json.dumps(b) in json.dumps(v) for b in bad)}
        bad |= more
        grew = bool(more)
    keep = []
    for held in items:
        if any(json.dumps(b) in json.dumps(held["item"]) for b in bad):
            unmapped.append(f"{what(held)}: its faces or edges are not those to_xcaf kept it on; left out")
        else:
            keep.append(held)
    return {**fragment, "items": keep}


def _one_unit_each(units: dict[str, list], pmi: dict[str, Any]) -> dict[str, Any]:
    """One definition of each unit (haecceity refuses two ids for the millimetre, say): a restored
    item's unit that is defined already is referred to by the id there."""
    names: dict[str, str] = {}
    for kind, listed in units.items():
        seen: dict[str, str] = {}
        keep = []
        for u in listed:
            key = repr(u["value"])
            if key in seen:
                names[u["id"]] = seen[key]
            else:
                seen[key] = u["id"]
                keep.append(u)
        listed[:] = keep

    def renamed(value):
        if isinstance(value, str):
            return names.get(value, value)
        if isinstance(value, list):
            return [renamed(v) for v in value]
        if isinstance(value, dict):
            return {k: renamed(v) for k, v in value.items()}
        return value

    return renamed(pmi) if names else pmi
