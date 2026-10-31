# xcaf-pmi

**Turn the GD&T in an OpenCascade document (`.xbf`) into an AP242 STEP file with semantic PMI**,
the form that CAD, CAM and inspection tools read.

If your application builds parts with OpenCascade and keeps its dimensions and tolerances in an
XCAF document (text-to-cad's cadgen does), xcaf-pmi reads them out and
[haecceity](https://github.com/pzfreo/quiddity-rust) (in the `quiddity` package) writes them into
the STEP as AP242, in one step.

## Install

```bash
pip install git+https://github.com/pzfreo/xcaf-pmi        # Python 3.11+, brings OCP and quiddity
```

## Make an AP242 STEP

```bash
xcaf-pmi part.xbf -o part.step
```

`part.step` has the part's geometry, face names and colours, and its GD&T as semantic PMI.
haecceity reads the file back before it is written and reports any difference. Anything that
could not be carried over is printed, one line each, rather than dropped silently; `--strict`
fails instead, writing nothing.

Advanced: `--step geometry.step` writes the geometry alone (no PMI), `--haecceity part.pmi.json`
the PMI as haecceity's JSON, and `--json found.json` the GD&T as read, in OCCT's terms.

## From Python

```python
from xcaf_pmi import to_step

step = to_step("part.xbf")                 # AP242 STEP bytes; the document may also be bytes
open("part.step", "wb").write(step)

step, report = to_step("part.xbf", report=True)
for line in report["unmapped"]:
    print("not carried over:", line)
print(report["quiddity"]["differences"])    # haecceity's read-back check: [] when all is kept
```

`to_step(..., strict=True)` raises `xcaf_pmi.NotCarriedOver` (its `unmapped` lists what) instead
of leaving anything out, and haecceity's refusals raise `quiddity.PmiError`. `part=` picks the
part when the document holds several. `read`, `export_step` and `to_haecceity` are the steps on
their own. `read` and `to_step` also accept an XmlXCAF `.xml` document.

## What is carried over

- **Datums**, including point, line, rectangle and circle datum targets.
- **Dimensions:** sizes (diameter, radius, thickness …) and linear distances, with ± tolerances,
  ISO 286 fits (e.g. ⌀10 H7) or as basic dimensions.
- **Geometric tolerances:** all fifteen kinds, with their datum references, a diameter zone and
  maximum or least material condition.
- **Notes**, on the part, on faces, or on a dimension or tolerance. A note has one owner in the
  PMI: one also on something else is listed as not carried over for that.
- **Material**, with its density stated in g/cm³. OCCT's own STEP writer gets that unit wrong
  (gram³·cm²), so readers ignore its density; this route writes it correctly.
- **Names:** your item names (e.g. `thickness`, `hole-position`) become the PMI's ids, and your face
  names are kept in the STEP, so the PMI points at faces by name.

Not yet: area datum targets, other tolerance modifiers, views, and the document's own drawn
callouts (graphical PMI).

**Tested on text-to-cad's `pmi_plate`:** the AP242 made this way has the same datums, dimensions and
tolerances, on the same faces, as cadgen's own AP242 export. It adds the two notes cadgen's STEP
leaves out, a stable id for each item, and the material's density in a unit readers accept. The
callouts are haecceity's own layout: the positions chosen in the document are not carried yet.

## More

- The PMI JSON format (`haecceity.pmi/1`): its
  [reference](https://github.com/pzfreo/quiddity-rust/blob/main/crates/haecceity/docs/pmi-json.md)
  and [JSON Schema](https://github.com/pzfreo/quiddity-rust/blob/main/crates/haecceity/schema/haecceity.pmi-1.json).
- To add manufacturing intent to a STEP that has none (fits, datums, tolerances, by answering a
  few questions): [Specify](https://pypi.org/project/specify-core/) (`pip install specify-core`),
  or [in the browser](https://editor.draftwright.io/specify).
- Developing xcaf-pmi: `pip install -e '.[test]'` and `pytest`, which includes the end-to-end tests
  through haecceity. `tests/make_plate.py` builds a test document
  through OCCT's own GD&T API, and `tests/fixtures/` holds text-to-cad's `pmi_plate` (MIT).

Apache-2.0.
