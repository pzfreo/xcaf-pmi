"""``xcaf-pmi DOC.xbf -o PART.step``: the document as AP242 STEP with its GD&T as semantic PMI.

Advanced: ``--step`` writes the geometry alone (no PMI), ``--haecceity`` the PMI as
haecceity.pmi/1 JSON, ``--json`` the GD&T as read, in OCCT's terms (``-`` for stdout)."""

from __future__ import annotations

import argparse
import json
import sys

from xcaf_pmi.ap242 import NotCarriedOver, to_step
from xcaf_pmi.haecceity import to_haecceity
from xcaf_pmi.reader import export_step, read


def _write_json(path: str, value) -> None:
    text = json.dumps(value, indent=1, ensure_ascii=False) + "\n"
    if path == "-":
        sys.stdout.write(text)
    else:
        with open(path, "w", encoding="utf-8") as out:
            out.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xcaf-pmi", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("document", help="an XCAF document: .xbf (BinXCAF) or .xml (XmlXCAF)")
    parser.add_argument("-o", "--output", help="the AP242 STEP to write, with semantic PMI")
    parser.add_argument("--part", type=int, default=0, help="the part whose GD&T is carried over (default 0)")
    parser.add_argument("--strict", action="store_true", help="fail, writing nothing, if any GD&T is not carried over")
    parser.add_argument("--step", help="advanced: also write the geometry alone as AP242 STEP, without PMI")
    parser.add_argument("--haecceity", help="advanced: also write the PMI as haecceity.pmi/1 JSON (faces named as in --step)")
    parser.add_argument("--json", help="advanced: also write the GD&T as read, in OCCT's terms ('-' for stdout)")
    args = parser.parse_args(argv)
    if not (args.output or args.step or args.haecceity or args.json):
        parser.error("nothing to write: give -o PART.step (or --step, --haecceity, --json)")
    try:
        problems: list[str] = []
        if args.output:
            written, report = to_step(args.document, args.part, strict=args.strict, report=True)
            with open(args.output, "wb") as out:
                out.write(written)
            problems = report["unmapped"]
            details = report["quiddity"]
            for difference in details["differences"]:
                print(f"xcaf-pmi: read back differently: {difference}", file=sys.stderr)
            for kind in ("read_findings", "writer_findings", "output_findings"):
                for finding in details[kind]:
                    print(f"xcaf-pmi: {kind.replace('_', ' ')[:-1]}: {json.dumps(finding, ensure_ascii=False)}",
                          file=sys.stderr)
        if args.step:
            export_step(args.document, args.step)
        if args.json or args.haecceity:
            found = read(args.document)
            if args.json:
                _write_json(args.json, found)
            if args.haecceity:
                mapped = to_haecceity(found, args.part)
                _write_json(args.haecceity, mapped["document"])
                problems = problems or mapped["unmapped"]
            elif not args.output:
                problems = found["unread"]
    except NotCarriedOver as error:
        print(f"xcaf-pmi: {error}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError) as error:  # PmiError is a ValueError
        print(f"xcaf-pmi: {error}", file=sys.stderr)
        return 1
    for line in problems:
        print(f"xcaf-pmi: not carried over: {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
