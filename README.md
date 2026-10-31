# xcaf-pmi

**Turn the GD&T in an OpenCascade document (`.xbf`) into an AP242 STEP file with semantic PMI**,
the form that CAD, CAM and inspection tools read, **and an AP242 STEP back into an OpenCascade
document**, with more of its PMI than OpenCascade's own reader keeps.

If your application builds parts with OpenCascade and keeps its dimensions and tolerances in an
XCAF document (text-to-cad's cadgen does), xcaf-pmi reads them out and
[haecceity](https://github.com/pzfreo/quiddity-rust) (in the `quiddity` package) writes them into
the STEP as AP242, in one step.

No GD&T in your document yet? xcaf-pmi only carries what is there. To add it, give the STEP to
[Specify](https://pypi.org/project/specify-core/) (`pip install specify-core`, or
[in the browser](https://editor.draftwright.io/specify)): it recognises the features and asks only
what is missing.

## Install

```bash
pip install git+https://github.com/pzfreo/xcaf-pmi        # Python 3.11+, brings OCP and quiddity
```

## Make an AP242 STEP

```bash
xcaf-pmi to-step part.xbf -o part.step
xcaf-pmi part.xbf -o part.step            # the same: an .xbf (or .xml) input goes to STEP
```

`part.step` has the part's geometry, face names and colours, its GD&T as semantic PMI, and a drawn
callout for each item. haecceity reads the file back before it is written and reports any
difference.

What it prints, on stderr:
- `not carried over: …`: something in the document that has no place in the PMI. `--strict`
  fails on these instead, writing nothing.
- `read back differently: …`: haecceity's read-back found the file says something other than what
  was sent. Also fails `--strict`.
- `read finding: …`, `writer finding: …`, `output finding: …`: information about how something was
  read or written (e.g. a free-text note kept as semantic text, or a datum target described as the
  CAx-IF practice asks where AP242's own rules disagree). Nothing is lost.

Advanced: `--step geometry.step` writes the geometry alone (no PMI), `--haecceity part.pmi.json`
the PMI as haecceity's JSON, and `--json found.json` the GD&T as read, in OCCT's terms.

## Make an XCAF document from an AP242 STEP

```bash
xcaf-pmi to-xcaf part.step -o part.xbf
xcaf-pmi part.step -o part.xbf            # the same: a .step or .stp input goes to XCAF
```

`part.xbf` has the part's geometry, names and colours as OpenCascade reads them, and the STEP's
PMI as XCAF GD&T on its faces: dimensions with their tolerances, limits, fits, modifiers and
qualifiers; geometric tolerances with their magnitudes, modifiers and datum systems; datums
(also those no tolerance refers to) and datum targets; notes; material and density; user-defined
attributes; and each item's drawn callout where the STEP has one. `--part N` takes only one
part's PMI from a STEP with several (by default, every part's).

What it prints, on stderr:
- `not carried over: …`: something in the STEP's PMI that XCAF has no form for (a thread, a
  surface texture, a general tolerance, a composite frame, the end of a projected tolerance zone,
  an item placed only on supplemental geometry …).
- `read finding: …`: how haecceity read the STEP: what it repaired (OCCT's malformed density unit,
  say), read leniently, or could not read. Nothing it reads is dropped without one.
- `faces: … matched by entity`: the STEP's faces are numbered differently from OpenCascade's; they
  were matched by the STEP entity each came from (by their geometry where that fails).

**What XCAF cannot hold is kept on the document**, as haecceity's JSON on the item's XCAF label
(the part's, for an item with none), so `to-step` restores it and the STEP → XCAF → STEP round
trip keeps it. Other XCAF readers do not see it: to them it is an attribute they do not know.

**Compared with OpenCascade's own GD&T reader** (`STEPCAFControl_Reader` with GD&T on), on NIST's
PMI test models (against NIST's expected PMI), Specify's output and cadgen's plate, `to-xcaf`
gets as much or more right in every category, and keeps the notes and materials OpenCascade's
reader drops. The exceptions: two NIST models (STC-06, STC-09) are refused whole by quiddity 0.4's
reader, and on OpenCascade's own export of cadgen's plate quiddity refuses the position tolerance
(OpenCascade writes its diameter zone as a runout zone with no angle; the finding says so).
`python tests/gaps.py` prints the counts.


```python
from xcaf_pmi import to_step

step = to_step("part.xbf")                 # AP242 STEP bytes; the document may also be bytes
open("part.step", "wb").write(step)

step, report = to_step("part.xbf", report=True)   # or an open XCAF document
for line in report["unmapped"]:
    print("not carried over:", line)
print(report["quiddity"]["differences"])    # haecceity's read-back check: [] when all is kept
```

The other way:

```python
from xcaf_pmi import to_xcaf, save

doc = to_xcaf("part.step")                 # an OCP TDocStd_Document; the STEP may also be bytes
save(doc, "part.xbf")

doc, report = to_xcaf("part.step", report=True)
print(report["unmapped"])                  # what XCAF has no form for (kept for to_step)
print(report["findings"])                  # haecceity's findings on reading the STEP
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
- **Drawn callouts:** each item gets a callout in haecceity's layout, linked to it as the CAx-IF
  practice asks, so CAD readers that show graphical PMI show it.

Not yet: area datum targets, other tolerance modifiers, saved views, and the callout *positions*
chosen in the document (the callouts are laid out afresh).

**Tested on text-to-cad's `pmi_plate`:** the AP242 made this way has the same datums, dimensions and
tolerances, on the same faces, as cadgen's own AP242 export. It adds the two notes cadgen's STEP
leaves out, a stable id for each item, and the material's density in a unit readers accept.
NIST's STEP File Analyzer (5.41) reads the same semantic PMI from both; on this route it also
finds the density valid (OCCT's export fails with "the length unit exponent should be -3"), no
duplicate datum system, and every callout as graphical PMI (none on cadgen's export, whose
callouts carry no names).

## Limits

- A document with several parts is mapped one part at a time (`part=`); this has not yet been
  tested on a multi-part document.
- A document given as bytes is read through a temporary file (OCCT's in-memory BinXCAF reader is
  unusable from Python).
- `to-xcaf` needs every PMI item quiddity 0.4 reads: a file it refuses (NIST's STC-06 and STC-09,
  over their attributes' names) is refused whole.
- Where OpenCascade reads a part as a solid with surfaces beside it (some NIST models), PMI on those
  surfaces is carried into XCAF but not back to STEP.

## More

- The PMI JSON format (`haecceity.pmi/1`): its
  [reference](https://github.com/pzfreo/quiddity-rust/blob/main/crates/haecceity/docs/pmi-json.md)
  and [JSON Schema](https://github.com/pzfreo/quiddity-rust/blob/main/crates/haecceity/schema/haecceity.pmi-1.json).
- To add manufacturing intent to a STEP that has none (fits, datums, tolerances, by answering a
  few questions): [Specify](https://pypi.org/project/specify-core/) (`pip install specify-core`),
  or [in the browser](https://editor.draftwright.io/specify).
- Developing xcaf-pmi: `pip install -e '.[test]'` and `pytest`, which includes the end-to-end tests
  through haecceity. `tests/make_plate.py` builds a test document
  through OCCT's own GD&T API, and `tests/fixtures/` holds text-to-cad's `pmi_plate` (MIT), NIST's
  CTC-01 with NIST's expected PMI, and three of Specify's outputs (see `tests/fixtures/README.md`).
  The other test files are fetched once from pinned commits (`tests/files.py`) into
  `~/.cache/xcaf-pmi` (or `$XCAF_PMI_CACHE`); tests needing them are skipped when offline.

Apache-2.0.
