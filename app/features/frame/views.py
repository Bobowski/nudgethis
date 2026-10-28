from stario import h
from stario.datastar import at, data
from stario.markup import HtmlElement, svg

from app.common.shell import page
from app.features.frame.data import Message
from app.features.frame.urls import ACT, FRAME_LIVE, SAY
from app.features.home.urls import HOME
from app.features.shots.urls import SHOT

ACTION_LABELS = {"ship": "Ship", "not_yet": "Not yet"}

INK_LOOP = svg.Svg(
    {"viewBox": "0 0 48 12", "class": "inkloop", "aria-hidden": "true"},
    svg.Path({"d": "M2 8 C 10 2, 16 12, 24 7 S 40 3, 46 8"}),
)


def message_li(m: Message, current: str) -> HtmlElement:
    tag = h.Span({"class": "tag"}, m.app) if m.app != current else None
    if m.role == "you":
        return h.Li(
            {"class": "msg you"},
            tag,
            h.P(m.text) if m.text else None,
            h.Span(
                {"class": "thumbs"},
                *[
                    h.A(
                        {"href": SHOT.href(s), "target": "_blank"},
                        h.Img({"src": SHOT.href(s), "alt": "shot"}),
                    )
                    for s in m.shots
                ],
            )
            if m.shots
            else None,
        )
    return h.Li(
        {"class": "msg nudge"},
        tag,
        h.P(m.text),
        h.Form(
            {"class": "acts"},
            data.on(
                "submit",
                at.post(ACT.href(current), include=["tab", "message_id", "action"]),
                prevent=True,
            ),
            *[
                h.Button(
                    {"type": "submit", "class": f"act {a}"},
                    data.on("click", f"$message_id = {m.id}; $action = '{a}'"),
                    ACTION_LABELS.get(a, a),
                )
                for a in m.actions
            ],
        )
        if m.actions
        else None,
    )


def render(
    messages: list[Message],
    name: str,
    url: str,
    working: bool,
    rev: int,
    tab: str,
) -> HtmlElement:
    return page(
        f"nudgethis · {name}",
        h.Div(
            {"id": "frame"},
            data.signals(
                {
                    "tab": tab,
                    "text": "",
                    "shots": [],
                    "message_id": 0,
                    "action": "",
                    "_rev": rev,
                    "_pod": False,
                    "_hint": "",
                },
                if_missing=True,
            ),
            data.init(
                "$_pod = matchMedia('(min-width: 900px)').matches; "
                + at.get(FRAME_LIVE.href(name), retry="always")
            ),
            data.effect("app.frame.rev($_rev)"),
            data.on("pagehide", "app.snap.stop()", target="window"),
            h.Header(
                {"id": "strip"},
                h.A({"href": HOME.href(), "class": "home"}, name),
                h.Span({"class": "appurl"}, url),
            ),
            h.Div(
                {"class": "stage"},
                h.Div(
                    {"class": "bezel"},
                    h.Iframe(
                        {
                            "id": "app-frame",
                            "src": url,
                            "title": name,
                        },
                        data.ignore_morph(),
                        data.init("app.frame.bind(el); app.snap.bind(el)"),
                    ),
                    h.Div(
                        {"id": "shipmark", "class": "shipmark", "aria-hidden": "true"},
                        data.preserve_attr("class"),
                        data.init("app.frame.mark(el)"),
                        svg.Svg(
                            {"viewBox": "0 0 24 24"},
                            svg.Path({"d": "M4 12.5 10 18 20 6"}),
                        ),
                    ),
                    h.Div(
                        {"id": "ink", "class": "ink"},
                        data.ignore_morph(),
                        data.init("app.ink.mount(el)"),
                        h.Canvas({"class": "inkcanvas"}),
                        h.Div(
                            {"class": "inktools"},
                            *[
                                h.Button(
                                    {"type": "button", "data-tool": tool},
                                    data.on("click", f"app.ink.tool('{tool}')"),
                                    label,
                                )
                                for tool, label in (
                                    ("marker", "Draw"),
                                    ("arrow", "Arrow"),
                                    ("box", "Box"),
                                    ("text", "Text"),
                                )
                            ],
                            h.Button(
                                {"type": "button"},
                                data.on("click", "app.ink.undo()"),
                                "Undo",
                            ),
                            h.Button(
                                {"type": "button"},
                                data.on("click", "app.ink.cancel()"),
                                "Cancel",
                            ),
                            h.Button(
                                {"type": "button", "class": "done"},
                                data.on("click", "app.ink.done()"),
                                "Done",
                            ),
                        ),
                    ),
                    h.Button(
                        {"type": "button", "class": "pill"},
                        data.show("!$_pod"),
                        data.on("click", "$_pod = true"),
                        INK_LOOP if working else None,
                        "Nudge",
                    ),
                ),
                h.Aside(
                    {"id": "pod"},
                    data.show("$_pod"),
                    h.Header(
                        {"class": "podhead"},
                        h.Span({"class": "podtitle"}, "Nudge"),
                        h.Button(
                            {"type": "button", "class": "close"},
                            data.on("click", "$_pod = false"),
                            "Close",
                        ),
                    ),
                    h.Ol(
                        {"id": "msgs"},
                        data.init("el.pod ??= app.pod(el)"),
                        *(
                            [message_li(m, name) for m in messages]
                            or [
                                h.Li(
                                    {"class": "empty"},
                                    "Snap the app, draw on it, say what you want.",
                                )
                            ]
                        ),
                        h.Li({"class": "working"}, INK_LOOP) if working else None,
                    ),
                    h.Form(
                        {"id": "composer"},
                        data.on(
                            "submit",
                            at.post(SAY.href(name), include=["tab", "text", "shots"]),
                            prevent=True,
                        ),
                        data.indicator("_sending"),
                        h.P(
                            {"class": "hint", "role": "status"},
                            data.show("$_hint"),
                            data.text("$_hint"),
                        ),
                        h.Div(
                            {"class": "pend"},
                            data.show("$shots.length > 0"),
                            *[
                                h.Span(
                                    {"class": "pendshot"},
                                    data.show(f"$shots.length > {i}"),
                                    h.Img(
                                        {"alt": f"shot {i + 1}"},
                                        data.attr(
                                            "src",
                                            f"$shots.length > {i} && $shots[{i}]",
                                        ),
                                    ),
                                    h.Button(
                                        {"type": "button", "class": "unshot"},
                                        data.on(
                                            "click",
                                            f"$shots = $shots.filter((s, j) => j !== {i})",
                                        ),
                                        "×",
                                    ),
                                )
                                for i in range(2)
                            ],
                        ),
                        h.Div(
                            {"class": "composerow"},
                            h.Button(
                                {"type": "button", "class": "snap"},
                                data.on(
                                    "click",
                                    "app.snap.go(v => $shots = v, h => $_hint = h)",
                                ),
                                data.attr("disabled", "$_sending"),
                                "Snap",
                            ),
                            h.Textarea(
                                {
                                    "rows": "1",
                                    "maxlength": 2000,
                                    "placeholder": "Say what you want…",
                                    "aria-label": "message",
                                },
                                data.bind("text"),
                                data.on(
                                    "keydown",
                                    "evt.key === 'Enter' && !evt.shiftKey"
                                    " && (evt.preventDefault(),"
                                    " el.form.requestSubmit())",
                                ),
                            ),
                            h.Button(
                                {"type": "submit", "class": "send"},
                                data.attr(
                                    "disabled",
                                    "$_sending || ($text.trim() === '' && $shots.length === 0)",
                                ),
                                "Send",
                            ),
                        ),
                        h.Input(
                            {"type": "file", "accept": "image/*", "hidden": True},
                            data.init("app.snap.input(el)"),
                            data.on(
                                "change",
                                "app.snap.pick(evt, v => $shots = v); $_hint = ''",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
