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
  the order haecceity numbers them, with each face's name, surface type, area and centroid), and
  the datums, dimensions and geometric tolerances with the faces they apply to. Anything it
  cannot interpret is listed in `unread`, not dropped.

The JSON is an intermediate form in OCCT's own vocabulary (`xcaf-pmi.intermediate/0`).
`to_haecceity` maps it to haecceity's PMI JSON (`haecceity.pmi/1`, quiddity-rust#142, a draft
under review), referring to faces by the names the STEP carries. haecceity then writes the PMI
onto the STEP (`quiddity pmi json import`, from a quiddity built with `--features json`).
Anything without a mapping yet is listed, not guessed.

On text-to-cad's `pmi_plate`, the PMI haecceity writes this way matches cadgen's own AP242
export item for item (datums, dimensions with their basic flags and tolerances, the five
tolerances, on the same faces), and adds the document's two notes, which cadgen's STEP leaves
out. `QUIDDITY=/path/to/quiddity pytest` runs that route as a test.

## Status

Prototype, tested on text-to-cad's `pmi_plate` as cadgen writes it (`tests/fixtures`) and on a
plate built through OCCT's own GD&T API. Read:

- datums (name, modifiers, target flag);
- dimensions (type, value, ± tolerance signed as the STEP states it or a range, basic,
  descriptions, qualifier, modifiers, both sides' faces);
- geometric tolerances (type, value, zone, material condition, modifiers, datum references);
- notes (their text) and views (name, projection, direction, up, section, the GD&T each shows).

Not yet: classes of tolerance (fits), datum target geometry, what a note is attached to, and the
GD&T's graphical presentation.

A part kept as an assembly's prototype (as cadgen keeps every part) is read through its
prototype, where its GD&T and face names are.

## Notes

OCP cannot hand back the document `TDocStd_Application.Open` fills, nor the attribute
`FindAttribute` finds; the reader works round both as cadgen does (the retrieval driver, and
`XCAFDoc_*.Set_s` on a label checked to hold the attribute).

`tests/make_plate.py` builds the test document through OCCT's own GD&T API, so the tests need
no other CAD package.

Apache-2.0.
