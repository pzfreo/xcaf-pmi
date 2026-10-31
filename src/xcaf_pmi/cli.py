"""``xcaf-pmi to-step DOC.xbf -o PART.step``: the document as AP242 STEP with its GD&T as
semantic PMI. ``xcaf-pmi to-xcaf PART.step -o DOC.xbf``: the STEP as an XCAF document with its
PMI as XCAF GD&T. Without a verb, the input's extension picks the direction.

to-step, advanced: ``--step`` writes the geometry alone (no PMI), ``--haecceity`` the PMI as
haecceity.pmi/1 JSON, ``--json`` the GD&T as read, in OCCT's terms (``-`` for stdout)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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


VERBS = ("to-step", "to-xcaf")
_TO_STEP = (".xbf", ".xml")
_TO_XCAF = (".step", ".stp")


_VALUED = {"-o", "--output", "--part", "--step", "--haecceity", "--json"}


def _input(argv: list[str]) -> str | None:
    """The input named in ``argv``: its first argument that is neither an option nor an
    option's value."""
    after_option = False
    for a in argv:
        if after_option:
            after_option = False
        elif a in _VALUED:
            after_option = True
        elif not a.startswith("-") or a == "-":
            return a
    return None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in VERBS:
        verb, argv = argv[0], argv[1:]
        return to_xcaf_main(argv) if verb == "to-xcaf" else to_step_main(argv)
    given = _input(argv)
    if given is None:
        out = sys.stdout if any(a in ("-h", "--help") for a in argv) else sys.stderr
        print("usage: xcaf-pmi to-step DOC.xbf -o PART.step [options]\n"
              "       xcaf-pmi to-xcaf PART.step -o DOC.xbf [--part N]\n"
              "       xcaf-pmi INPUT -o OUTPUT   (the direction from INPUT's extension)\n\n" + __doc__, file=out)
        return 0 if out is sys.stdout else 2
    suffix = Path(given).suffix.lower()
    if suffix in _TO_STEP:
        return to_step_main(argv)
    if suffix in _TO_XCAF:
        return to_xcaf_main(argv)
    print(f"xcaf-pmi: {given}: neither an XCAF document (.xbf, .xml) nor a STEP (.step, .stp); "
          "name the direction: xcaf-pmi to-step DOC.xbf -o PART.step, "
          "or xcaf-pmi to-xcaf PART.step -o DOC.xbf", file=sys.stderr)
    return 2


def to_xcaf_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="xcaf-pmi to-xcaf",
                                     description="The STEP as an XCAF document (.xbf), its PMI as XCAF GD&T.")
    parser.add_argument("step", help="an AP242 STEP (.step, .stp)")
    parser.add_argument("-o", "--output", required=True, help="the XCAF document to write (.xbf)")
    parser.add_argument("--part", type=int, help="only this part's PMI (default: every part's)")
    args = parser.parse_args(argv)
    if Path(args.output).suffix.lower() != ".xbf":
        parser.error(f"{args.output}: the output is an .xbf document")
    from xcaf_pmi.from_step import to_xcaf
    from xcaf_pmi.geometry import save
    try:
        doc, report = to_xcaf(args.step, args.part, report=True)
        save(doc, args.output)
    except (ValueError, RuntimeError) as error:  # PmiError is a ValueError
        print(f"xcaf-pmi: {error}", file=sys.stderr)
        for finding in getattr(error, "findings", None) or []:
            print(f"xcaf-pmi: read finding: {json.dumps(finding, ensure_ascii=False)}", file=sys.stderr)
        return 1
    for method in report["faces"]:
        if method != "index":
            print(f"xcaf-pmi: faces: haecceity's numbering differs from OCCT's; matched by {method}", file=sys.stderr)
    for line in report["unmapped"]:
        print(f"xcaf-pmi: not carried over: {line}", file=sys.stderr)
    for finding in report["findings"]:
        print(f"xcaf-pmi: read finding: {json.dumps(finding, ensure_ascii=False)}", file=sys.stderr)
    return 0


def to_step_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="xcaf-pmi to-step", description=__doc__,
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
