"""What an XCAF document's GD&T gets right, counted against what the STEP states.

Both readings of a STEP (OCCT's own GD&T reader, and ``to_xcaf``) are taken through ``read``'s
intermediate form and reduced to comparable facts, by category; so is what the file states:
NIST's expected PMI for its test models (from the STEP File Analyzer, as quiddity-rust's
``tests/fixtures/ap242/nist/*.expected.json`` record it), the document a STEP was made from, or,
for other files, haecceity's own reading. A fact is right when the reading has it too; each fact
counts once for each time it is stated.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

CATEGORIES = [
    ("dimensions", "dimensions: values"),
    ("dimension tolerances", "dimensions: values and tolerances"),
    ("tolerances", "geometric tolerances: kinds and magnitudes"),
    ("modifiers", "geometric tolerances: with their modifiers"),
    ("datums", "datums"),
    ("datum systems", "datum systems"),
    ("notes", "notes"),
    ("material", "material"),
    ("density", "density"),
    ("names", "item names (ids)"),
]

TOLERANCE = {
    "Angularity": "angularity", "CircularRunout": "circular_runout", "Coaxiality": "coaxiality",
    "Concentricity": "concentricity", "Cylindricity": "cylindricity", "Flatness": "flatness",
    "ProfileOfLine": "line_profile", "Parallelism": "parallelism", "Perpendicularity": "perpendicularity",
    "Position": "position", "Roundness": "roundness", "Straightness": "straightness",
    "ProfileOfSurface": "surface_profile", "Symmetry": "symmetry", "TotalRunout": "total_runout",
}
# A modifier is counted as a token: NIST's symbol where it has one (M, L, P, F, T, ST), else
# haecceity's name. OCCT's modifiers (its enumerations' suffixes) are first named as haecceity
# names them (xcaf_pmi.haecceity's tables), so every modifier both readings know compares.
from xcaf_pmi.haecceity import DATUM_MODIFIER as _OCCT_DATUM, TOLERANCE_MODIFIER as _OCCT_TOLERANCE

_HMOD = {"maximum_material_requirement": "M", "least_material_requirement": "L", "statistical_tolerance": "ST",
         "free_state": "F", "tangent_plane": "T"}
_HDATUM = {"maximum_material_requirement": "M", "least_material_requirement": "L", "free_state": "F"}
MODIFIER = {"All_Around": "all around", "All_Over": "all over",
            **{occt: _HMOD.get(name, name) for occt, name in _OCCT_TOLERANCE.items()}}
DATUM_MODIFIER = {occt: _HDATUM.get(name, name) for occt, name in _OCCT_DATUM.items()}
ANGULAR = {"Location_Angular", "Size_Angular"}


def _r(value: float | None) -> float | None:
    return None if value is None else round(value + 0.0, 4) + 0.0


def xcaf_facts(found: dict[str, Any], part: int | None = None) -> dict[str, Counter]:
    """The facts of ``read``'s result (one part's, or all)."""
    on_part = lambda item: part is None or any(r.get("part") == part for r in item.get("faces", []))
    out = {key: Counter() for key, _ in CATEGORIES}
    for d in found["dimensions"]:
        if d["type"] in ("DimensionPresentation", "CommonLabel"):
            continue  # graphics only, or a label: no dimension stated
        kind = "angle" if d["type"] in ANGULAR else "length"
        nominal = None if "range" in d else _r(d["value"])
        out["dimensions"][(kind, nominal)] += 1
        if d.get("basic"):
            form: tuple = ("basic",)
        elif "fit" in d:
            fit = d["fit"]
            form = ("fit", (fit["letter"].upper() if fit["hole"] else fit["letter"].lower()) + fit["grade"].removeprefix("IT"))
        elif "tolerance" in d:
            form = ("±", _r(d["tolerance"]["upper"]), _r(d["tolerance"]["lower"]))
        elif "range" in d:
            form = ("limits", _r(d["range"]["lower"]), _r(d["range"]["upper"]))
        else:
            form = ("none",)
        out["dimension tolerances"][(kind, nominal, form)] += 1
    for t in found["tolerances"]:
        kind = TOLERANCE.get(t["type"], t["type"])
        value = _r(t["value"])
        out["tolerances"][(kind, value)] += 1
        refs = t.get("datum_refs") or [{"name": n, "modifiers": []} for n in t["datums"]]
        mods = {MODIFIER.get(m.split("GeomToleranceModif_")[-1], m.split("GeomToleranceModif_")[-1]) for m in t["modifiers"]}
        if t["material"] in ("M", "L"):
            mods.add(t["material"])
        if t.get("zone_modifier") == "Projected":
            mods.add("P")
        if t.get("maximum"):
            mods.add("max")
        for r in refs:
            for m in r["modifiers"]:
                mods.add(f"{r['name']}:{DATUM_MODIFIER.get(m.split('DatumSingleModif_')[-1], m.split('DatumSingleModif_')[-1])}")
        if mods:
            out["modifiers"][(kind, value, frozenset(mods))] += 1
        letters = tuple(dict.fromkeys(r["name"] for r in refs))
        if letters:
            out["datum systems"][letters] += 1
    # A datum once for each part it is on (OCCT keeps a datum for each tolerance referring to it).
    for _, letter in {(tuple(sorted({r.get("part") for r in d["faces"]})), d["name"]) for d in found["datums"] if d["name"]}:
        out["datums"][letter] += 1
    for n in found.get("notes", []):
        out["notes"][" ".join(n["text"].split())] += 1
    for i, p in enumerate(found["parts"]):
        m = p.get("material")
        if (part is None or i == part) and m and m["name"]:
            out["material"][m["name"]] += 1
            if m["density"]:
                out["density"][(m["name"], round(m["density"], 4))] += 1
    for group in ("dimensions", "tolerances"):
        for item in found[group]:
            if item.get("name") and not item["name"].startswith("DGT:"):
                out["names"][item["name"]] += 1
    return out


# What a STEP states, as haecceity reads it ---------------------------------------------------

_HKIND = {f"{v}_tolerance": v for v in TOLERANCE.values()}
_MM = {"millimetre": 1.0, "inch": 25.4, "metre": 1000.0, "centimetre": 10.0, "micrometre": 0.001, "foot": 304.8}


def haecceity_facts(document: dict[str, Any], names: bool = False) -> dict[str, Counter]:
    """The facts of a ``haecceity.pmi/1`` document. Item ids count as names only with ``names``
    (a file's own ids; haecceity makes up the others)."""
    pmi = document["pmi"]
    length = {u["id"]: _MM.get(u["value"], 1.0) if isinstance(u["value"], str) else float(u["value"]["other"]["metres"]) * 1000
              for u in document["units"]["length"]}

    def value(v):
        if v is None:
            return None
        (kind, q), = v["quantity"].items()
        return _r(float(q["value"]) * (length.get(q["unit"], 1.0) if kind == "length" else 1.0))

    out = {key: Counter() for key, _ in CATEGORIES}
    features = {f["id"]: f["value"] for f in pmi["features"]}
    letters = {d["id"]: d["value"]["label"] for d in pmi["datums"]}
    for item in pmi["dimensions"]:
        d = item["value"]
        (form_kind, k), = d["kind"].items()
        name = k["kind"] if isinstance(k["kind"], str) else k["kind"]["other"]
        kind = "angle" if name == "angle" or (d["nominal"] and "angle" in d["nominal"]["quantity"]) else "length"
        t = d["tolerance"]
        nominal = None if isinstance(t, dict) and "limits" in t else value(d["nominal"])
        out["dimensions"][(kind, nominal)] += 1
        if t in ("basic", "none"):
            form: tuple = (t,)
        elif "deviations" in t:
            form = ("±", value(t["deviations"]["upper"]), value(t["deviations"]["lower"]))
        elif "limits" in t:
            form = ("limits", value(t["limits"]["lower"]), value(t["limits"]["upper"]))
        else:
            c = t["fit"]["class"]
            letter = c["deviation"]["letter"]
            form = ("fit", (letter.upper() if c["deviation"]["of"] == "hole" else letter.lower()) + c["grade"])
        out["dimension tolerances"][(kind, nominal, form)] += 1
        if names:
            out["names"][item["id"]] += 1
    for item in pmi["tolerances"]:
        t = item["value"]
        kind = _HKIND.get(t["kind"], t["kind"])
        magnitude = value(t["magnitude"])
        out["tolerances"][(kind, magnitude)] += 1
        mods = {_HMOD.get(m, m) for m in t["modifiers"]}
        target = t["target"]
        if isinstance(target, dict) and "feature" in target:
            f = features.get(target["feature"], {})
            if "group" in f and f["group"]["kind"] == "all_around_shape_aspect":
                mods.add("all around")
        if "all_over" in t["auxiliary"]:
            mods.add("all over")
        if t["zone"] and t["zone"]["projected"]:
            mods.add("P")
        if t["maximum"]:
            mods.add("max")
        system = []
        for compartment in t["datums"] or []:
            for ref in compartment["references"]:
                letter = letters.get(ref["datum"], ref["datum"])
                system.append(letter)
                for m in [*ref["modifiers"], *compartment["modifiers"]]:
                    if "simple" in m:
                        mods.add(f"{letter}:{_HDATUM.get(m['simple'], m['simple'])}")
        if mods:
            out["modifiers"][(kind, magnitude, frozenset(mods))] += 1
        if system:
            out["datum systems"][tuple(dict.fromkeys(system))] += 1
        if names:
            out["names"][item["id"]] += 1
    for letter in {d["value"]["label"] for d in pmi["datums"]}:
        out["datums"][letter] += 1
    for n in pmi["notes"]:
        out["notes"][" ".join(n["value"]["text"].split())] += 1
    m = pmi["material"]
    if m:
        out["material"][m["id"]] += 1
        if m["density"]:
            unit = {u["id"]: u["value"] for u in document["units"]["density"]}.get(m["density"]["unit"], [])
            factor = 1.0
            grams = {"gram": 1.0, "kilogram": 1000.0}
            cm = {"centimetre": 1.0, "millimetre": 0.1, "metre": 100.0, "inch": 2.54}
            for n, e in unit:
                factor *= (grams.get(n) or cm.get(n, 1.0)) ** float(e)
            out["density"][(m["id"], round(float(m["density"]["value"]) * factor, 4))] += 1
    return out


# What NIST states, from the STEP File Analyzer's expected PMI ------------------------------------

_SYMBOL_MODS = {"Ⓜ": "M", "Ⓛ": "L", "Ⓟ": "P", "Ⓕ": "F", "Ⓣ": "T", "<ST>": "ST"}
_NUMBER = r"[+-]?\s*(?:\d*\.\d+|\d+)"


class Near(float):
    """A value as printed: right within half its last digit."""

    def __new__(cls, printed: str, scale: float = 1.0):
        printed = printed.replace(" ", "")
        decimals = len(printed.split(".")[1]) if "." in printed else 0
        value = super().__new__(cls, float(printed) * scale + 0.0)
        value.eps = 0.5 * 10 ** -decimals * scale + 1e-9
        return value


def _number(text: str, scale: float = 1.0) -> Near | None:
    found = re.search(_NUMBER, text)
    return None if found is None else Near(found.group(0), scale)


def _dimension(text: str, scale: float):
    """A dimension as SFA prints it (``2X ⌀.594 +.012/-.002``): its kind, nominal and tolerance."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    first = re.sub(r"^\d+X\s+", "", lines[0])
    angle = "°" in first
    k = 1.0 if angle else scale
    first = re.sub(r"^\(?(S?⌀|S?R|CR)", "", first).rstrip(")").replace("°", "")
    kind = "angle" if angle else "length"
    limits = re.match(r"(\d*\.\d+|\d+)-(\d*\.\d+|\d+)", first)
    if limits:
        return kind, None, ("limits", Near(limits.group(1), k), Near(limits.group(2), k))
    nominal = _number(first, k)
    rest = first[re.search(_NUMBER, first).end():]
    if "±" in rest:
        t = re.search(_NUMBER, rest.split("±")[1]).group(0)
        return kind, nominal, ("±", Near(t, k), Near("-" + t, k))
    fit = re.match(r"\s*([A-Za-z]{1,2})(\d{1,2})\b", rest)
    if fit:
        return kind, nominal, ("fit", fit.group(1) + fit.group(2))
    signed = re.findall(_NUMBER, " ".join([rest, *lines[1:2]]))
    if len(signed) >= 2:
        upper, lower = signed[:2]
        lower = lower.replace(" ", "")
        return kind, nominal, ("±", Near(upper, k), Near(lower if lower.startswith("-") or float(lower) == 0 else "-" + lower, k))
    return kind, nominal, ("none",)


def nist_facts(expected: dict[str, Any]) -> dict[str, Counter]:
    """The facts of NIST's expected PMI for one of its models (quiddity-rust's ``expected.json``)."""
    scale = 25.4 if "INCH" in " ".join(expected["units"].get("unit_context_length_units", {})) else 1.0
    out = {key: Counter() for key, _ in CATEGORIES}
    letters: set[str] = set()
    for row in expected["rows"]:
        kind, text = row["cells"]["A"], row["cells"].get("B", "")
        if kind == "dimensional_characteristic_representation":
            k, nominal, form = _dimension(text, scale)
            out["dimensions"][(k, nominal)] += 1
            out["dimension tolerances"][(k, nominal, form)] += 1
        elif kind == "datum_system":
            pass  # the systems are counted from the tolerances that use them
        elif kind in ("placed_datum_target_feature", "datum_target"):
            letters.add(re.search(r"[A-Z]+", text).group(0))
        elif "_tolerance" in kind:
            tolerance = max((t for t in TOLERANCE.values() if f"{t}_tolerance" in kind), key=len)
            frame = next(line for line in text.split("\n") if " | " in line)
            cells = [c.strip() for c in frame.split("|")]
            mods = set()
            if cells[0] in ("⌮", "⭩◎"):  # all around, all over
                mods.add("all around" if cells[0] == "⌮" else "all over")
                cells = cells[1:]
            magnitude = cells[1]
            mods |= {token for symbol, token in _SYMBOL_MODS.items() if symbol in magnitude}
            value = _number(magnitude.split("/")[0].split("Ⓟ")[0], scale)
            system = []
            for cell in cells[2:]:
                if "MAX" in cell:
                    mods.add("max")
                    continue
                if not cell:
                    continue
                for letter in re.findall(r"[A-Z]+(?=[^A-Z]|$)", cell.split(" ")[0]):
                    system.append(letter)
                    letters.add(letter)
                    mods |= {f"{letter}:{token}" for symbol, token in _SYMBOL_MODS.items() if symbol in cell}
            out["tolerances"][(tolerance, value)] += 1
            if mods:
                out["modifiers"][(tolerance, value, frozenset(mods))] += 1
            if system:
                out["datum systems"][tuple(dict.fromkeys(system))] += 1
            for found in re.findall(r"\[([A-Z]+)\]", text):
                letters.add(found)
    for letter in letters:
        out["datums"][letter] += 1
    return out


def _agree(stated, read) -> bool:
    if isinstance(stated, Near):
        return isinstance(read, float) and abs(read - stated) <= stated.eps
    if isinstance(stated, tuple):
        return isinstance(read, tuple) and len(read) == len(stated) and all(map(_agree, stated, read))
    return stated == read


def score(truth: dict[str, Counter], reading: dict[str, Counter]) -> dict[str, tuple[int, int]]:
    """For each category, (facts the reading gets right, facts stated). Each fact read matches
    one fact stated."""
    out = {}
    for key, _ in CATEGORIES:
        left = list(reading[key].elements())
        right = 0
        for fact in truth[key].elements():
            at = next((i for i, read in enumerate(left) if _agree(fact, read)), None)
            if at is not None:
                right += 1
                del left[at]
        out[key] = (right, sum(truth[key].values()))
    return out


def missed(truth: dict[str, Counter], reading: dict[str, Counter], key: str) -> list:
    """The facts stated that the reading does not have."""
    left = list(reading[key].elements())
    out = []
    for fact in truth[key].elements():
        at = next((i for i, read in enumerate(left) if _agree(fact, read)), None)
        if at is None:
            out.append(fact)
        else:
            del left[at]
    return out


def step_facts(step) -> dict[str, Counter]:
    """The facts of every part of a STEP, as haecceity reads them."""
    from quiddity import pmi

    from xcaf_pmi.from_step import _parts

    parts = _parts(step)
    out = {key: Counter() for key, _ in CATEGORIES}
    for i in range(len(parts)):
        for key, facts in haecceity_facts(pmi.read(step, part=None if len(parts) == 1 else i)).items():
            out[key] += facts
    return out


def placed(step, part: int | None = None) -> dict[str, Any]:
    """haecceity's reading of a STEP (one part of it), each reference to a feature replaced by
    where the feature is: the surface, area and centre of each of its faces and the curve, length
    and centre of each edge, as OCCT reads them, and each unit by its definition. Two files'
    readings then compare by place, not by their ids or numbering of faces and edges."""
    import json

    from quiddity import pmi

    from xcaf_pmi import geometry as g
    from xcaf_pmi.from_step import _choose, _parts

    theirs = _parts(step)
    index = part or 0
    document = pmi.read(step, part=index if len(theirs) > 1 else None)
    # OCCT's reader fails on a string longer than its scanner's buffer (quiddity 0.4 writes its
    # map of ids as one): its geometry is read from a copy with such strings emptied.
    import re
    import tempfile
    from pathlib import Path

    text = Path(step).read_bytes()
    short = re.sub(rb"'(?:[^']|'')*'", lambda m: b"''" if len(m.group(0)) > 8000 else m.group(0), text)
    if short != text:
        step = Path(tempfile.mkdtemp()) / "geometry.step"
        step.write_bytes(short)
    doc, entity_of = g.read_step_faces(step)
    shape, offset = _choose(doc, theirs, index)
    face_map = g.faces(step, shape, entity_of, offset)["faces"]
    features = {f["id"]: f["value"] for f in document["pmi"]["features"]}
    used = [i["edge"] for v in features.values() for i in v.get("items", []) if "edge" in i]
    edge_map = g.edges(step, shape, entity_of, used, face_map, offset)["edges"]
    whole = g.shape_map(shape.shape)
    r = lambda v: round(v + 0.0, 3) + 0.0

    def item(i):
        if "face" in i:
            k = face_map[i["face"]] if isinstance(i["face"], int) and i["face"] < len(face_map) else None
            if k is None:
                return ["face", None]
            area, centre = g._props(whole.FindKey(k + 1))
            return ["face", r(area), *map(r, centre)]
        if "edge" in i:
            j = edge_map.get(i["edge"])
            return ["edge", None] if j is None else ["edge", g.edge_print(shape.edges[j][1])[0], *map(r, g.edge_print(shape.edges[j][1])[1:])]
        return i

    def where(id, seen=()):
        v = features[id]
        if "items" in v:
            return sorted((item(i) for i in v["items"]), key=json.dumps)
        kind, members = ("group", v["group"]) if "group" in v else ("derived", v["derived"])
        return {kind: {k: x for k, x in members.items() if k not in ("members", "from")},
                "on": sorted((where(m, seen + (id,)) for m in members.get("members") or members.get("from") or []
                              if m not in seen), key=json.dumps)}

    units = {u["id"]: u["value"] for listed in document["units"].values() for u in listed}
    # A datum by its letter, a target by its letter and number; a number by its value.
    letters = {d["id"]: d["value"]["label"] for d in document["pmi"]["datums"]}
    letters |= {t: f"{d['value']['label']}{n['value']['number']}" for d in document["pmi"]["datums"]
                for t in d["value"]["targets"] for n in document["pmi"]["datum_targets"] if n["id"] == t}

    def number(text):
        try:
            return float(text)
        except ValueError:
            return None

    def resolved(value, key=None):
        if isinstance(value, str):
            if number(value) is not None and key in ("value", None):
                return repr(round(number(value), 9) + 0.0)
            return where(value) if value in features else letters.get(value, units.get(value, value))
        if isinstance(value, list):
            return [resolved(v) for v in value]
        if isinstance(value, dict):
            if set(value) == {"unit", "value"} and units.get(value["unit"]) in _MM and number(value["value"]) is not None:
                # A length in millimetres, whatever unit the file states it in.
                return {"unit": "millimetre",
                        "value": repr(round(number(value["value"]) * _MM[units[value["unit"]]], 6) + 0.0)}
            return {k: resolved(v, k) for k, v in value.items() if k != "id"}
        return value

    # Each item keeps its id beside it ("id"), to name it; compare items without it.
    return {group: [{**resolved(x), "id": x.get("id")} if isinstance(x, dict) else x for x in listed]
            if isinstance(listed, list) else resolved(listed)
            for group, listed in document["pmi"].items() if group not in ("features", "geometry")}


def placed_all(step) -> dict[str, list]:
    """``placed`` of every part of a STEP, together."""
    from xcaf_pmi.from_step import _parts

    n = len(_parts(step))
    out: dict[str, list] = {}
    for i in range(n):
        for group, listed in placed(step, i if n > 1 else None).items():
            if isinstance(listed, list):
                out.setdefault(group, []).extend(listed)
    return out


def lost(before: dict[str, list], after: dict[str, list]) -> tuple[list, list]:
    """What ``before`` states that ``after`` does not, as (group, id), and what ``after`` states
    that ``before`` does not: items compared by their content and place, not their ids."""
    import json

    text = lambda x: json.dumps({k: v for k, v in x.items() if k != "id"} if isinstance(x, dict) else x, sort_keys=True)
    gone, more = [], []
    for group in sorted(set(before) | set(after)):
        left = [(text(x), x) for x in after.get(group, [])]
        for x in before.get(group, []):
            at = next((i for i, (t, _) in enumerate(left) if t == text(x)), None)
            if at is None:
                gone.append((group, x.get("id") if isinstance(x, dict) else None))
            else:
                del left[at]
        more += [(group, x.get("id") if isinstance(x, dict) else None) for _, x in left]
    return gone, more


def occt_step(xbf) -> bytes:
    """An XCAF document as OCCT's own STEP writer makes it, GD&T and material included (cadgen's
    export)."""
    import io

    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType

    from xcaf_pmi.reader import open_document

    writer = STEPCAFControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetIVal_s("write.stepcaf.subshapes.name", 1)
    for mode in (writer.SetNameMode, writer.SetColorMode, writer.SetDimTolMode, writer.SetMaterialMode):
        mode(True)
    writer.Transfer(open_document(xbf), STEPControl_StepModelType.STEPControl_AsIs)
    out = io.BytesIO()
    writer.WriteStream(out)
    return out.getvalue()


def row(step, truth: dict[str, Counter]) -> dict[str, tuple[int, int, int]]:
    """One file's line of the gap table: for each category, (OCCT's reader right, ``to_xcaf``
    right, stated). Where haecceity refuses a file or an item, to_xcaf takes OCCT's reading of it."""
    from xcaf_pmi.from_step import to_xcaf
    from xcaf_pmi.geometry import read_step
    from xcaf_pmi.reader import read_document

    native = score(truth, xcaf_facts(read_document(read_step(step, gdt=True), str(step))))
    ours = score(truth, xcaf_facts(read_document(to_xcaf(step), str(step))))
    return {key: (native[key][0], ours[key][0], native[key][1]) for key, _ in CATEGORIES}


# Where each file's truth comes from: NIST's expected PMI, haecceity's own reading of a STEP
# Specify or draftwright wrote (so a measure of what to_xcaf keeps of it, not of whether it is
# right), and cadgen's document for cadgen's plate.
SOURCES = {"NIST (expected PMI)": "nist", "Specify and draftwright (haecceity's own reading)": "haecceity",
           "cadgen (its document)": "cadgen"}


def source(name: str) -> str:
    return "cadgen" if name.startswith("cadgen") else "nist" if name.startswith("nist_") and "_asme1_" in name else "haecceity"


def totals(rows: dict[str, dict[str, tuple[int, int, int]]]) -> dict[str, tuple[int, int, int]]:
    """For each truth source, (OCCT's reader right, to_xcaf right, stated) over every category."""
    out = {}
    for label, key in SOURCES.items():
        cells = [cell for name, r in rows.items() if source(name) == key for cell in r.values()]
        out[label] = tuple(sum(c[i] for c in cells) for i in range(3))
    return out


def table(tmp) -> dict[str, dict[str, tuple[int, int, int]]]:
    """The gap table over every test file there is (``files``), and cadgen's plate both ways."""
    from pathlib import Path

    import files
    from xcaf_pmi import to_step
    from xcaf_pmi.reader import read

    out = {}
    for name in files.NIST + files.SPECIFY + files.DRAFTWRIGHT_FILES:
        path = files.step(name)  # a file not fetched skips (or fails) the whole table, not its row
        stated = files.expected(name)
        out[name] = row(path, nist_facts(stated) if stated else step_facts(path))
    xbf = Path(__file__).parent / "fixtures" / "cadgen_pmi_plate.xbf"
    truth = xcaf_facts(read(xbf))
    for label, data in (("cadgen plate, OCCT's export", occt_step(xbf)), ("cadgen plate, to_step", to_step(xbf))):
        path = Path(tmp) / (label.split(", ")[1].replace("'", "").replace(" ", "_") + ".step")
        path.write_bytes(data)
        out[label] = row(path, truth)
    return out


def render(rows: dict[str, dict[str, tuple[int, int, int]]]) -> str:
    """The table as Markdown: per category, OCCT's reader and ``to_xcaf`` right of stated."""
    head = "| category | " + " | ".join(rows) + " | total |"
    lines = [head, "|" + "---|" * (len(rows) + 2)]
    for key, label in CATEGORIES:
        cells, totals = [], [0, 0, 0]
        for r in rows.values():
            native, ours, n = r[key]
            cells.append(f"{native} / {ours} of {n}" if n else "–")
            totals = [totals[0] + native, totals[1] + ours, totals[2] + n]
        if totals[2]:
            lines.append(f"| {label} | " + " | ".join(cells) + f" | **{totals[0]} / {totals[1]} of {totals[2]}** |")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    import tempfile
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    with tempfile.TemporaryDirectory() as folder:
        rows = table(folder)
    print(render(rows))
    print()
    for label, (native, ours, n) in totals(rows).items():
        print(f"{label}: OCCT's reader {native}, to_xcaf {ours}, of {n}")
    print()
    print(repr(rows))
