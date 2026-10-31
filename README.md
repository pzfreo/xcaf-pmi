# xcaf-pmi

Read the GD&T in an OpenCascade XCAF document (`.xbf`, or XmlXCAF `.xml`), and write the
document's geometry as AP242 STEP without PMI, so that
[haecceity](https://github.com/pzfreo/quiddity-rust) can add semantic PMI that CAD and
inspection tools read.

Any OCCT application that keeps GD&T in an XCAF document can use it: text-to-cad's cadgen is
the first.

```bash
pip install -e .
xcaf-pmi part.xbf -o part.pmi.json --step part.step --haecceity part.haecceity.json
quiddity pmi json import part.step part.haecceity.json -o part-with-pmi.step
```

```python
from xcaf_pmi import read, export_step, to_haecceity

pmi = read("part.xbf")                  # datums, dimensions and tolerances, with their faces
export_step("part.xbf", "part.step")    # geometry, names and colours; no GD&T
doc = to_haecceity(pmi)["document"]     # haecceity.pmi/1, faces named as in part.step
```

## The two outputs

- **The STEP** is the document's shapes, names, colours and layers, written by OCCT as AP242
  with its GD&T export off. Faces keep the names the document gives them.
- **The JSON** lists each part's faces (OCCT's order, which is the order of the STEP's faces and
  the order haecceity numbers them, with each face's name, surface type, area and centroid), the
  datums, dimensions and geometric tolerances with the faces they apply to, and the notes with
  what each is on. Anything it cannot interpret is listed in `unread`, not dropped.

The JSON is an intermediate form in OCCT's own vocabulary (`xcaf-pmi.intermediate/0`).
`to_haecceity` maps it to haecceity's PMI JSON (`haecceity.pmi/1`, quiddity-rust#142's v1
contract, in review as quiddity-rust#147), referring to faces by the names the STEP carries. haecceity then writes the PMI
onto the STEP (`quiddity pmi json import`, from a quiddity built with `--features json`).
Anything without a mapping yet is listed, not guessed.

On text-to-cad's `pmi_plate`, the PMI haecceity writes this way matches cadgen's own AP242
export item for item (datums, dimensions with their basic flags and tolerances, the five
tolerances, on the same faces), and adds the document's two notes, which cadgen's STEP leaves
out: the general note on the part, and the flag note on the hole's face (it also names
`hole-diameter`, which one owner cannot carry). Reading the written STEP back returns the same items under the same ids (`thickness`,
`hole-position` …), which are cadgen's own item names. `QUIDDITY=/path/to/quiddity pytest` runs that route as a test.

## Status

Prototype, tested on text-to-cad's `pmi_plate` as cadgen writes it (`tests/fixtures`) and on a
plate built through OCCT's own GD&T API (with a fit, a datum of targets and notes on a face, a
tolerance and the part). Read:

- datums (name, modifiers), and datum targets (OCCT keeps each as a datum of its datum's name:
  type, number, length and width, placement);
- dimensions (type, value, ± tolerance signed as the STEP states it or a range, class of
  tolerance (fit: hole or shaft, letter, grade), basic, descriptions, qualifier, modifiers, both
  sides' faces);
- geometric tolerances (type, value, zone, material condition, modifiers, datum references);
- notes (their text, and what each is on: faces, by sub-shape index or face label; a datum,
  dimension or tolerance; or a whole part) and views (name, projection, direction, up, section,
  the GD&T each shows).

Mapped to `haecceity.pmi/1` as well: a fit as `DimTolerance.fit` (its ISO 286 class, and limits
where a ± tolerance stands beside it); point, line, rectangle and circle targets as
`datum_targets` with their datum's `targets`; a note's owner as `Note.on`. haecceity allows a note
one owner: the faces it is on (one feature), else the first dimension, tolerance or datum target
it annotates; a note on a whole part has none. What else a note is on is listed as not carried.

Not yet: area targets, datum and dimension modifiers, and the GD&T's graphical presentation.

haecceity (quiddity-rust#147 as tested) does not yet write two of these back: a datum target
whose decimals end in `.0` (it writes `-30.0` as `-30.` and refuses its own read-back), and a note
owned by a dimension or tolerance (it writes it outside AP242's `characterized_definition`). The
end-to-end tests mark both as expected failures.

A part kept as an assembly's prototype (as cadgen keeps every part) is read through its
prototype, where its GD&T and face names are.

## Notes

OCP cannot hand back the document `TDocStd_Application.Open` fills, nor the attribute
`FindAttribute` finds; the reader works round both as cadgen does (the retrieval driver, and
`XCAFDoc_*.Set_s` on a label checked to hold the attribute). A dimension's class of tolerance is
read from the object's `DumpJson`, since OCP cannot fill `GetClassOfTolerance`'s reference
arguments. OCCT names every unnamed dimension and tolerance alike (`DGT:Dimension`), so an item
whose name is not unique keeps its document entry as its haecceity id.

`tests/make_plate.py` builds the test document through OCCT's own GD&T API, so the tests need
no other CAD package.

Apache-2.0.
