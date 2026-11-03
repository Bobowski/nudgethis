from stario.markup import render as html

from app.common.markdown import render
from app.features.frame.handlers import brief_of


def md(text: str) -> str:
    return "".join(html(b) for b in render(text))


def test_a_coder_report_becomes_headings_lists_and_inline_marks():
    out = md(
        "Added **14 illustrated asteroids** to the belt.\n\n"
        "### What changed\n"
        "- **SVG rocks** with warm gradients.\n"
        "- **Motion**: the same **`orbit` / `upright`** pattern.\n"
        "  It keeps the belt.\n\n"
        "1. one\n2. two"
    )
    assert "<p>Added <strong>14 illustrated asteroids</strong> to the belt.</p>" in out
    assert "<h4>What changed</h4>" in out
    assert "<ul><li><strong>SVG rocks</strong> with warm gradients.</li>" in out
    assert "<strong><code>orbit</code> / <code>upright</code></strong>" in out
    assert "pattern. It keeps the belt.</li></ul>" in out
    assert "<ol><li>one</li><li>two</li></ol>" in out
    assert "**" not in out and "###" not in out


def test_code_fences_and_links():
    out = md("```\nx = <b>1</b>\n```\n[docs](https://stario.dev) and [bad](javascript:alert(1))")
    assert "<pre><code>x = &lt;b&gt;1&lt;/b&gt;</code></pre>" in out
    assert 'href="https://stario.dev"' in out
    assert "javascript:" not in out.split("[bad]")[0] or "<a" not in out.split("[bad]")[1]


def test_html_in_the_text_is_escaped():
    out = md("<script>alert(1)</script> **<img src=x>**")
    assert "<script>" not in out and "<img" not in out


def test_an_unclosed_mark_stays_text():
    assert md("a **`pre") == "<p>a **`pre</p>"
    assert md("2 * 3 * 4") == "<p>2 * 3 * 4</p>"


def test_a_long_report_is_cut_at_a_line_break():
    report = "\n".join(f"- line {i} " + "x" * 50 for i in range(100))
    brief = brief_of(report)
    assert len(brief) < 2500
    assert brief.endswith("x\n\n…")
    assert brief_of("short") == "short"
