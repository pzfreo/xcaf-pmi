"""``xcaf-pmi DOC.xbf -o PMI.json [--step GEOMETRY.step] [--haecceity PMI.haecceity.json]``"""

from __future__ import annotations

import argparse
import json
import sys

from xcaf_pmi.haecceity import to_haecceity
from xcaf_pmi.reader import export_step, read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xcaf-pmi", description=__doc__)
    parser.add_argument("document", help="an XCAF document: .xbf (BinXCAF) or .xml (XmlXCAF)")
    parser.add_argument("-o", "--output", help="the GD&T as JSON (default: stdout)")
    parser.add_argument("--step", help="also write the geometry as AP242 STEP, without PMI")
    parser.add_argument("--haecceity", help="also write the PMI as haecceity.pmi/1 (faces named as in --step)")
    parser.add_argument("--part", type=int, default=0, help="the part --haecceity maps (default 0)")
    args = parser.parse_args(argv)
    try:
        found = read(args.document)
        if args.step:
            export_step(args.document, args.step)
    except (ValueError, RuntimeError) as error:
        print(f"xcaf-pmi: {error}", file=sys.stderr)
        return 1
    text = json.dumps(found, indent=1, ensure_ascii=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as out:
            out.write(text + "\n")
    else:
        print(text)
    problems = found["unread"]
    if args.haecceity:
        mapped = to_haecceity(found, args.part)
        with open(args.haecceity, "w", encoding="utf-8") as out:
            out.write(json.dumps(mapped["document"], indent=1, ensure_ascii=False) + "\n")
        problems = mapped["unmapped"]
    for line in problems:
        print(f"xcaf-pmi: not carried over: {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
