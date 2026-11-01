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
- `not carried over: …`: something in the document that has no place in the PMI, or that could
  not be checked (an edge whose number on the STEP written cannot be checked, say). `--strict`
  fails on these instead, writing nothing.
- `read back differently: …`: haecceity's read-back found the file says something other than what
  was sent. Also fails `--strict`.
- `read finding: …`, `writer finding: …`, `output finding: …`: information about how something was
  read or written (e.g. a free-text note kept as semantic text, or a datum target described as the
  CAx-IF practice asks where AP242's own rules disagree). Nothing is lost.

`--part N` carries only that part's GD&T; by default every part with PMI of its own has it
written on it.

Advanced: `--step geometry.step` writes the geometry alone (no PMI), `--haecceity part.pmi.json`
the PMI as haecceity's JSON, `--json found.json` the GD&T as read, in OCCT's terms, and
`--presentation part.presentation.json` (with `-o`) the document's own callouts and views.

Exit status, both ways: 0 written; 1 failed (an input that cannot be read, a part the file has
not, haecceity's refusal, an output that cannot be written); 2 a usage error; 3 `--strict` found
something not carried over, and nothing was written.

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
  say), read leniently, or could not read. Nothing it reads is dropped without one. A finding of
  kind `fallback` says haecceity refused a part, or did not read an item, and OpenCascade's own
  reading of it was taken instead.
- `faces: … matched by entity` (or `edges: …`): the STEP's faces or edges are numbered differently
  from OpenCascade's; they were matched by the STEP entity each came from (faces by their geometry
  where that fails, one to one). A face or edge that matches none, or more than one, is listed as
  not carried over and its items are kept unanchored, never placed on a guess.

**What XCAF cannot hold is kept on the document**, as haecceity's JSON on the item's XCAF label
(the part's, for an item with none), with the state of the item and of the faces it is on when it
was kept. `to-step` restores it where the document still states the same: an item edited since
is written as the document now has it, and what was kept for it is listed as not carried over.
Other XCAF readers do not see it: to them it is an attribute they do not know. What the round
trip STEP → XCAF → STEP still loses is listed, never dropped silently: items on surfaces
OpenCascade reads beside the solid, edges whose number haecceity gives cannot be checked, and
items haecceity's writer refuses.

**Compared with OpenCascade's own GD&T reader** (`STEPCAFControl_Reader` with GD&T on), on every
test file `to-xcaf` gets every category at least as right, and keeps the notes and materials
OpenCascade's reader drops: where haecceity refuses a file (quiddity 0.4 refuses NIST's STC-06
and STC-09 whole) or does not read an item (the position tolerance of OpenCascade's own export of
cadgen's plate, whose diameter zone it writes as a runout zone with no angle), `to-xcaf` takes
OpenCascade's reading of it. Facts right of those stated, OpenCascade's reader / `to-xcaf`:

| what the files state | OpenCascade | `to-xcaf` | stated |
|---|---|---|---|
| NIST's 7 PMI test models, against NIST's expected PMI | 590 | 611 | 738 |
| 7 of Specify's outputs and draftwright's spindle, against haecceity's own reading of them (what `to-xcaf` keeps, not whether it is right) | 171 | 224 | 232 |
| cadgen's plate, both exports, against cadgen's document | 44 | 55 | 66 |

`python tests/gaps.py` prints them by file and category.


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
of leaving anything out, and haecceity's refusals raise `quiddity.PmiError`. In a document of
several parts, each part with PMI of its own (GD&T, notes, material, or what `to-xcaf` kept) has
it written on its own part of the STEP, the parts matched to quiddity's by name and number of
faces; `part=` takes only one. A part's items on another part's faces or datums are left out and
listed. `read`, `export_step` and `to_haecceity` are the steps on their own. `read` and `to_step` also accept an XmlXCAF `.xml` document.

## What is carried over

- **Datums**, including point, line, rectangle, circle and area datum targets (an area as XCAF
  holds it, the target's shape, or the faces the target is on).
- **Dimensions:** sizes (diameter, radius, thickness …), linear distances and angles, with ±
  tolerances, limits, ISO 286 fits (e.g. ⌀10 H7) or as basic dimensions, and their modifiers and
  qualifiers.
- **Geometric tolerances:** all fifteen kinds, with their datum references (modifiers and common
  datums too), a diameter zone, maximum or least material condition, a maximum value, a runout
  zone's angle, all around, all over, and XCAF's other modifiers (free state, tangent plane,
  statistical, line element, common zone …).
- **Notes**, on the part, on faces, or on a dimension or tolerance. A note has one owner in the
  PMI: one also on something else is listed as not carried over for that.
- **Material**, with its density stated in g/cm³. OCCT's own STEP writer gets that unit wrong
  (gram³·cm²), so readers ignore its density; this route writes it correctly.
- **Names:** your item names (e.g. `thickness`, `hole-position`) become the PMI's ids, and your face
  names are kept in the STEP, so the PMI points at faces by name.
- **Drawn callouts:** each item gets a callout in haecceity's layout, linked to it as the CAx-IF
  practice asks, so CAD readers that show graphical PMI show it.

Not yet:
- **Projected tolerance zones.** AP242 needs to know where the projection ends, and XCAF holds only
  its length, so these are listed as not carried over.
- **Callout positions and saved views.** The callouts in the STEP are laid out afresh. The
  document's own callouts (where it places them, on their annotation planes, with their text
  points) and its saved views (camera and the items each shows) can be written out as
  haecceity's presentation JSON with `--presentation part.presentation.json` (with `-o`;
  `report["presentation"]` from Python). quiddity 0.4 cannot yet write that layout into the STEP
  in place of its own.

**Tested on text-to-cad's `pmi_plate`:** the AP242 made this way has the same datums, dimensions and
tolerances, on the same faces, as cadgen's own AP242 export. It adds the two notes cadgen's STEP
leaves out, a stable id for each item, and the material's density in a unit readers accept.
NIST's STEP File Analyzer (5.41) reads the same semantic PMI from both; on this route it also
finds the density valid (OCCT's export fails with "the length unit exponent should be -3"), no
duplicate datum system, and every callout as graphical PMI (none on cadgen's export, whose
callouts carry no names).

## Limits

- A document given as bytes is read through a temporary file (OCCT's in-memory BinXCAF reader is
  unusable from Python).
- Where quiddity 0.4 refuses a file (NIST's STC-06 and STC-09, over their attributes' names),
  `to-xcaf` has only OpenCascade's reading of its GD&T: no notes, no kept extras.
- quiddity 0.4 states no STEP entity for an edge: `to-xcaf` checks haecceity's edge numbers against
  the edges the STEP's PMI is on, and reports those it cannot check (two of NIST STC-10's).
- OpenCascade's STEP reader cannot read a string longer than its scanner's buffer; quiddity 0.4
  writes its map of item ids as one string, which on NIST's STC-10 is too long for it (47 kB).
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
