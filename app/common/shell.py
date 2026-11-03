from stario import h
from stario.datastar import ModuleScript, data
from stario.markup import HtmlElement, baked, svg

from app.assets import DATASTAR_JS, SCRIPTS, STYLE_CSS

# The moving ink line: Nudge or the coder is at work.
INK_LOOP = svg.Svg(
    {"viewBox": "0 0 48 12", "class": "inkloop", "aria-hidden": "true"},
    svg.Path({"d": "M2 8 C 10 2, 16 12, 24 7 S 40 3, 46 8"}),
)


@baked
def page(title: str, body: HtmlElement) -> HtmlElement:
    return h.HtmlDocument(
        {"lang": "en"},
        h.Head(
            h.Meta({"charset": "utf-8"}),
            # maximum-scale stops iOS zooming into a focused field and staying zoomed
            # after the keyboard closes; pinch zoom still works on iOS.
            h.Meta(
                {
                    "name": "viewport",
                    "content": "width=device-width, initial-scale=1, maximum-scale=1",
                }
            ),
            h.Title(title),
            h.Link({"rel": "stylesheet", "href": STYLE_CSS}),
            *[h.Script({"src": src, "defer": True}) for src in SCRIPTS],
            ModuleScript(DATASTAR_JS),
        ),
        h.Body(
            body,
            h.Output(
                {"id": "toast", "role": "status"},
                data.signals({"_toast": ""}, if_missing=True),
                data.show("$_toast"),
                data.text("$_toast"),
                data.effect("$_toast && setTimeout(() => $_toast = '', 4000)"),
            ),
        ),
    )
