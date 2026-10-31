# xcaf-pmi

**Turn the GD&T in an OpenCascade document (`.xbf`) into an AP242 STEP file with semantic PMI**,
the form that CAD, CAM and inspection tools read.

If your application builds parts with OpenCascade and keeps its dimensions and tolerances in an
XCAF document (text-to-cad's cadgen does), xcaf-pmi reads them out, and
[haecceity](https://github.com/pzfreo/quiddity-rust) writes them into the STEP as AP242.

## Install

```bash
pip install git+https://github.com/pzfreo/xcaf-pmi        # xcaf-pmi (Python 3.11+, brings OCP)
cargo install quiddity --features json                    # the quiddity command, which writes the PMI
```

## Make an AP242 STEP

```bash
xcaf-pmi part.xbf --step part.step --haecceity part.pmi.json
quiddity pmi json import part.step part.pmi.json -o part-ap242.step
```

1. `xcaf-pmi` writes the part's geometry as STEP (`part.step`, no PMI yet) and its GD&T as a PMI
   JSON file (`part.pmi.json`).
2. `quiddity` writes that PMI into the STEP, checks the file it wrote, and reports any difference.
   `part-ap242.step` is the result.

Anything xcaf-pmi could not carry over is printed, one line each, rather than dropped silently.
`quiddity pmi json validate part.pmi.json` checks the JSON on its own.

## From Python

```python
import json, subprocess
from xcaf_pmi import read, export_step, to_haecceity

pmi = read("part.xbf")
export_step("part.xbf", "part.step")
mapped = to_haecceity(pmi)
for line in mapped["unmapped"]:
    print("not carried over:", line)

with open("part.pmi.json", "w") as f:
    json.dump(mapped["document"], f)
subprocess.run(["quiddity", "pmi", "json", "import", "part.step", "part.pmi.json",
                "-o", "part-ap242.step"], check=True)
```

`read` also accepts an XmlXCAF `.xml` document.

## What is carried over

- **Datums**, and point, line, rectangle and circle datum targets (written once quiddity 0.2.8 is
  out; 0.2.7 refuses them).
- **Dimensions:** sizes (diameter, radius, thickness …) and linear distances, with ± tolerances,
  ISO 286 fits (e.g. ⌀10 H7) or as basic dimensions.
- **Geometric tolerances:** all fifteen kinds, with their datum references, a diameter zone and
  maximum or least material condition.
- **Notes**, on the part or on faces (on a dimension or tolerance once quiddity 0.2.8 is out).
- **Names:** your item names (e.g. `thickness`, `hole-position`) become the PMI's ids, and your face
  names are kept in the STEP, so the PMI points at faces by name.

Not yet: area datum targets, other tolerance modifiers, views, and the document's own drawn
callouts (graphical PMI).

**Tested on text-to-cad's `pmi_plate`:** the AP242 made this way has the same datums, dimensions and
tolerances, on the same faces, as cadgen's own AP242 export, and it also carries the two notes
that cadgen's STEP leaves out.

## More

- The PMI JSON format (`haecceity.pmi/1`): its
  [reference](https://github.com/pzfreo/quiddity-rust/blob/main/crates/haecceity/docs/pmi-json.md)
  and [JSON Schema](https://github.com/pzfreo/quiddity-rust/blob/main/crates/haecceity/schema/haecceity.pmi-1.json).
- To add manufacturing intent to a STEP that has none (fits, datums, tolerances, by answering a
  few questions): [Specify](https://pypi.org/project/specify-core/) (`pip install specify-core`),
  or [in the browser](https://editor.draftwright.io/specify).
- Developing xcaf-pmi: `pip install -e '.[test]'` and `pytest`. Set `QUIDDITY` to a quiddity binary
  to include the end-to-end test through haecceity. `tests/make_plate.py` builds a test document
  through OCCT's own GD&T API, and `tests/fixtures/` holds text-to-cad's `pmi_plate` (MIT).

Apache-2.0.
