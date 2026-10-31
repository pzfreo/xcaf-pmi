# Fixtures

`nist/` holds NIST's MBE PMI test model CTC-01 as AP242 (`nist_ctc_01_asme1_ap242-e1.stp.gz`) and
NIST's expected PMI for it from the STEP File Analyzer (`nist_ctc_01.expected.json`), both copied
from pzfreo/quiddity-rust at commit 11a540e7 (`tests/fixtures/ap242/nist/`). NIST states its
models "can be used without any restrictions" and asks for acknowledgement, which this is; use
does not imply a recommendation or endorsement by NIST.

`specify/` holds specify-core's output (commit cc341dd6) on three corpus parts, copied from
pzfreo/quiddity-rust at commit 11a540e7 (`tests/fixtures/ap242/specify/`): `spool_fits` on
CADGenBench's generated `flanged_spool_132` (Apache-2.0), `thumbwheel_thread_knurl` and
`bolt_thread_knurl` on the author's GRM-03 and GRM-05 (Apache-2.0).

`cadgen_pmi_plate.xbf` is text-to-cad's `models/examples/src/pmi_plate.py` built by cadgen 0.8.3
and exported with `cadgen export`, at commit eab58ee8 of
[earthtojake/text-to-cad#692](https://github.com/earthtojake/text-to-cad/pull/692)
(Amy's branch, `amywork777/text-to-cad-upstream`). It is used here under text-to-cad's MIT
licence, below.

```
MIT License

Copyright (c) 2026 Thompson Labs LLC

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
