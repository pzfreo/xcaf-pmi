"""``xcaf-pmi DOC.xbf -o PMI.json [--step GEOMETRY.step]``"""

from __future__ import annotations

import argparse
import json
import sys

from xcaf_pmi.reader import export_step, read


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xcaf-pmi", description=__doc__)
    parser.add_argument("document", help="an XCAF document: .xbf (BinXCAF) or .xml (XmlXCAF)")
    parser.add_argument("-o", "--output", help="the GD&T as JSON (default: stdout)")
    parser.add_argument("--step", help="also write the geometry as AP242 STEP, without PMI")
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
    for line in found["unread"]:
        print(f"xcaf-pmi: not read: {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
