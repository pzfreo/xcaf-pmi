# xcaf-pmi

Read the GD&T in an OpenCascade XCAF document (`.xbf`, or XmlXCAF `.xml`), and write the
document's geometry as AP242 STEP without PMI, so that
[haecceity](https://github.com/pzfreo/quiddity-rust) can add semantic PMI that CAD and
inspection tools read.

Any OCCT application that keeps GD&T in an XCAF document can use it: text-to-cad's cadgen is
the first.

```bash
pip install -e .
xcaf-pmi part.xbf -o part.pmi.json --step part.step
```

```python
from xcaf_pmi import read, export_step

pmi = read("part.xbf")                  # datums, dimensions and tolerances, with their faces
export_step("part.xbf", "part.step")    # geometry, names and colours; no GD&T
```

## The two outputs

- **The STEP** is the document's shapes, names, colours and layers, written by OCCT as AP242
  with its GD&T export off. Faces keep the names the document gives them.
- **The JSON** lists each part's faces (OCCT's order, which is the order of the STEP's faces and
  the order haecceity numbers them, with each face's name, surface type, area and centroid), and
  the datums, dimensions and geometric tolerances with the faces they apply to. Anything it
  cannot interpret is listed in `unread`, not dropped.

The JSON is an intermediate form in OCCT's own vocabulary (`xcaf-pmi.intermediate/0`). Its
mapping to haecceity's PMI JSON (`haecceity.pmi/1`, quiddity-rust#142) comes once that schema
is drafted; haecceity then writes the PMI onto the STEP.

## Status

Prototype. Read so far: datums (name, modifiers, target flag), dimensions (type, value, ±
tolerance or range, qualifier, modifiers, both sides' faces) and geometric tolerances (type,
value, zone, material condition, modifiers, datum references). Not yet: classes of tolerance
(fits), datum target geometry, datum systems' modifiers per compartment, notes, views and the
GD&T's graphical presentation.

## Notes

OCP cannot hand back the document `TDocStd_Application.Open` fills, nor the attribute
`FindAttribute` finds; the reader works round both as cadgen does (the retrieval driver, and
`XCAFDoc_*.Set_s` on a label checked to hold the attribute).

`tests/make_plate.py` builds the test document through OCCT's own GD&T API, so the tests need
no other CAD package.

Apache-2.0.
