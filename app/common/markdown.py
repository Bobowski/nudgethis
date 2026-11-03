"""The markdown that Nudge and the coder write, as HTML elements.

A small subset: headings, paragraphs, lists, fenced code, and inline code,
bold, italic, and links. Every piece of text goes through Stario's escaping;
a link keeps only an http(s) address. Anything else stays plain text.
"""

import re

from stario import h
from stario.markup import HtmlElement

INLINE = re.compile(
    r"`(?P<code>[^`\n]+)`"
    r"|\*\*(?P<bold>\S(?:.*?\S)?)\*\*"
    r"|\[(?P<label>[^\]\n]+)\]\((?P<href>https?://[^)\s]+)\)"
    r"|(?<![\w*])\*(?P<em>[^*\s](?:[^*\n]*?[^*\s])?)\*(?![\w*])"
    r"|(?<![\w_])_(?P<em2>[^_\s](?:[^_\n]*?[^_\s])?)_(?![\w_])"
)
FENCE = re.compile(r"^\s*```")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def inline(text: str) -> list[HtmlElement | str]:
    out: list[HtmlElement | str] = []
    at = 0
    for m in INLINE.finditer(text):
        if m.start() > at:
            out.append(text[at : m.start()])
        if m["code"] is not None:
            out.append(h.Code(m["code"]))
        elif m["bold"] is not None:
            out.append(h.Strong(*inline(m["bold"])))
        elif m["label"] is not None:
            out.append(
                h.A({"href": m["href"], "target": "_blank", "rel": "noopener"}, *inline(m["label"]))
            )
        else:
            out.append(h.Em(*inline(m["em"] if m["em"] is not None else m["em2"])))
        at = m.end()
    if at < len(text):
        out.append(text[at:])
    return out


def render(text: str) -> list[HtmlElement]:
    """The blocks of `text`, in order."""
    blocks: list[HtmlElement] = []
    para: list[str] = []
    items: list[str] = []
    ordered = False
    lines = text.replace("\r\n", "\n").split("\n")

    def flush() -> None:
        nonlocal para, items
        if para:
            blocks.append(h.P(*inline(" ".join(para))))
            para = []
        if items:
            tag = h.Ol if ordered else h.Ul
            blocks.append(tag(*[h.Li(*inline(item)) for item in items]))
            items = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if FENCE.match(line):
            flush()
            code: list[str] = []
            i += 1
            while i < len(lines) and not FENCE.match(lines[i]):
                code.append(lines[i])
                i += 1
            blocks.append(h.Pre(h.Code("\n".join(code))))
        elif not line.strip():
            flush()
        elif m := HEADING.match(line):
            flush()
            blocks.append(h.H4(*inline(m[1])))
        elif item := BULLET.match(line) or NUMBERED.match(line):
            is_ordered = item.re is NUMBERED
            if para or (items and is_ordered != ordered):
                flush()
            ordered = is_ordered
            items.append(item[1])
        elif items and line.startswith((" ", "\t")):
            items[-1] += " " + line.strip()
        else:
            if items:
                flush()
            para.append(line.strip())
        i += 1
    flush()
    return blocks
