"""0.80.0: the Shelly scripts without their comments and indentation, for the relay.

A Shelly script keeps the text of every function in its small heap (about 25 kB, shared by all its scripts), the
comments and the indentation too. This takes them out and leaves the code itself as it is: line by line (no line is
joined, so no statement can run into the next), strings untouched ('..' and ".." with their escapes; the scripts use
no template strings and no regular expressions).

    python3 guard/compact_js.py            # writes guard/shelly/hc_lite.min.js from hc_lite.js
"""

from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SRC = HERE / "shelly" / "hc_lite.js"
OUT = HERE / "shelly" / "hc_lite.min.js"
HEAD = "// HC Thermostat Lite {ver} - compact (generated from hc_lite.js: python3 guard/compact_js.py). Read the full,\n" \
       "// commented source in hc_lite.js; paste this one into the Shelly's Scripts (it needs less of the relay's memory).\n"


def _strip_line(line: str) -> str:
    out, q, i = [], None, 0
    while i < len(line):
        c = line[i]
        if q:
            out.append(c)
            if c == "\\" and i + 1 < len(line):
                out.append(line[i + 1])
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"":
            q = c
            out.append(c)
        elif c == "/" and line[i + 1:i + 2] == "/":
            break
        else:
            out.append(c)
        i += 1
    if q:
        raise ValueError(f"an open string: {line!r}")
    return "".join(out).strip()


def compact(code: str) -> str:
    lines = (_strip_line(ln) for ln in code.splitlines())
    return "\n".join(ln for ln in lines if ln) + "\n"


def version(code: str) -> str:
    i = code.find('sv: "')
    return code[i + 5:code.index('"', i + 5)] if i >= 0 else "?"


def build() -> str:
    code = SRC.read_text("ascii")
    return HEAD.format(ver=version(code)) + compact(code)


if __name__ == "__main__":
    OUT.write_text(build(), "ascii")
    print(f"{OUT.name}: {len(SRC.read_bytes())} -> {len(OUT.read_bytes())} bytes")
    sys.exit(0)
