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

SNAP_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Path({"d": "M4 8.5h3.2L9 6h6l1.8 2.5H20V19H4z"}),
    svg.Circle({"cx": "12", "cy": "13.5", "r": "3.2"}),
)

SEND_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Path({"d": "M12 19V5M6 11l6-6 6 6"}),
)


def acts(m: Message, current: str) -> HtmlElement:
    return h.Form(
        {"class": "acts"},
        data.on(
            "submit",
            at.post(ACT.href(current), include=["tab", "message_id", "action"])
            + "; $_peek = false",
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


def message_li(m: Message, current: str) -> HtmlElement:
    tag = h.Span({"class": "tag"}, m.app) if m.app != current else None
    if m.thinking:
        return h.Li({"class": "working"}, tag, INK_LOOP)
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
        acts(m, current) if m.actions else None,
    )


def render(
    messages: list[Message],
    name: str,
    url: str,
    working: bool,
    rev: int,
    tab: str,
) -> HtmlElement:
    here = [m for m in messages if m.app == name]
    replies = [m for m in here if m.role == "nudge" and not m.thinking]
    latest = replies[-1] if replies else None
    pending = next((m for m in reversed(replies) if m.actions and m.change_status == "ready"), None)
    if any(m.thinking for m in here):
        state, label = "busy", "Thinking"
    elif working:
        state, label = "busy", "Working"
    elif pending:
        state, label = "ready", "Ready to ship"
    else:
        state, label = "idle", name
    latest_id = latest.id if latest else 0
    unread = f"$_seen < {latest_id}"
    peek = pending or latest
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
                    "_dock": "top",
                    "_seen": 0,
                    "_compose": False,
                    "_peek": False,
                    "_history": "",
                    "_hint": "",
                },
                if_missing=True,
            ),
            data.init(at.get(FRAME_LIVE.href(name), retry="always")),
            data.effect("app.frame.rev($_rev)"),
            data.on("pagehide", "app.snap.stop()", target="window"),
            data.on(
                "keydown",
                "evt.key === 'Escape' && ($_compose = false, $_peek = false, $_history = '')",
                target="window",
            ),
            h.Aside(
                {"id": "history"},
                data.classes({"open": "$_history !== ''", "right": "$_history === 'right'"}),
                h.Header(
                    {"class": "histhead"},
                    h.A({"href": HOME.href(), "class": "home"}, "nudgethis"),
                    h.Span({"class": "appname"}, name),
                    h.Span({"class": "appurl"}, url),
                ),
                h.Ol(
                    {"id": "msgs"},
                    data.init("el.pod ??= app.pod(el)"),
                    *(
                        [message_li(m, name) for m in messages]
                        or [
                            h.Li(
                                {"class": "empty"},
                                "Pull the pill to say what you want. Hold it to snap.",
                            )
                        ]
                    ),
                    h.Li({"class": "working"}, INK_LOOP)
                    if working and not (messages and messages[-1].thinking)
                    else None,
                ),
                h.Button(
                    {"type": "button", "class": "glass chip write"},
                    data.on("click", "$_history = ''; $_compose = true"),
                    "Say something",
                ),
            ),
            h.Div(
                {"class": "stage"},
                data.classes(
                    {
                        "aside-left": "$_history === 'left'",
                        "aside-right": "$_history === 'right'",
                    }
                ),
                h.Iframe(
                    {"id": "app-frame", "src": url, "title": name},
                    data.ignore_morph(),
                    data.init("app.frame.bind(el); app.snap.bind(el)"),
                ),
                h.Div(
                    {
                        "id": "nudge",
                        "data-latest": latest_id,
                        **({"data-pending": "1"} if pending else {}),
                    },
                    data.class_("bottom", "$_dock === 'bottom'"),
                    data.init(
                        "$_dock = app.pill.load('dock', 'top'); $_seen = app.pill.load('seen', 0)"
                    ),
                    data.effect("app.pill.save('dock', $_dock); app.pill.save('seen', $_seen)"),
                    data.on("pill-dock", "$_dock = evt.detail"),
                    data.on("pill-pull", "$_peek = false; $_compose = true"),
                    data.on(
                        "pill-swipe",
                        "$_peek = false; $_history = evt.detail; $_seen = +el.dataset.latest",
                    ),
                    data.on(
                        "pill-tap",
                        "$_peek || $_seen < +el.dataset.latest || el.dataset.pending"
                        " ? ($_peek = !$_peek, $_seen = +el.dataset.latest)"
                        " : ($_compose = !$_compose)",
                    ),
                    data.on(
                        "pill-hold",
                        "app.snap.go(v => ($shots = v, $_compose = true),"
                        " h => ($_hint = h, $_compose = true))",
                    ),
                    data.on(
                        "blur",
                        "$_peek = false; !$text.trim() && !$shots.length && ($_compose = false)",
                        target="window",
                    ),
                    h.Button(
                        {
                            "type": "button",
                            "class": "glass pill",
                            "data-state": state,
                            "aria-label": "Nudge: tap, pull, swipe, or hold",
                        },
                        data.preserve_attr(["style", "class"]),
                        data.init("app.pill.mount(el)"),
                        h.Span(
                            {"class": "orb"},
                            data.class_("unread", unread),
                        ),
                        h.Span(
                            {"id": "shipmark", "class": "shipmark", "aria-hidden": "true"},
                            data.preserve_attr("class"),
                            data.init("app.frame.mark(el)"),
                            svg.Svg(
                                {"viewBox": "0 0 24 24"},
                                svg.Path({"d": "M4 12.5 10 18 20 6"}),
                            ),
                        ),
                        h.Span(
                            {"class": "label"},
                            data.show(f"!({unread})") if state == "idle" else None,
                            label,
                        ),
                        h.Span({"class": "label"}, data.show(unread), "New reply")
                        if state == "idle"
                        else None,
                        INK_LOOP if state == "busy" else None,
                    ),
                    h.Div(
                        {"class": "glass card peek"},
                        data.show("$_peek && !$_compose"),
                        h.P(peek.text) if peek else h.P({"class": "dim"}, "Nothing new."),
                        acts(peek, name) if peek and peek.actions else None,
                        h.Button(
                            {"type": "button", "class": "chip"},
                            data.on("click", "$_peek = false; $_history = 'left'"),
                            "History",
                        ),
                    ),
                    h.Form(
                        {"id": "composer", "class": "glass card"},
                        data.show("$_compose"),
                        data.on(
                            "submit",
                            at.post(SAY.href(name), include=["tab", "text", "shots"])
                            + "; $_compose = false",
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
                                        data.attr("src", f"$shots.length > {i} && $shots[{i}]"),
                                    ),
                                    h.Button(
                                        {
                                            "type": "button",
                                            "class": "unshot",
                                            "aria-label": "Remove",
                                        },
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
                                {"type": "button", "class": "round snap", "aria-label": "Snap"},
                                data.on(
                                    "click",
                                    "app.snap.go(v => $shots = v, h => $_hint = h)",
                                ),
                                data.attr("disabled", "$_sending"),
                                SNAP_ICON,
                            ),
                            h.Textarea(
                                {
                                    "rows": "1",
                                    "maxlength": 2000,
                                    "placeholder": "Say what you want…",
                                    "aria-label": "message",
                                },
                                data.bind("text"),
                                data.effect("$_compose && setTimeout(() => el.focus(), 60)"),
                                data.on(
                                    "keydown",
                                    "evt.key === 'Enter' && !evt.shiftKey"
                                    " && (evt.preventDefault(), el.form.requestSubmit())",
                                ),
                            ),
                            h.Button(
                                {"type": "submit", "class": "round send", "aria-label": "Send"},
                                data.attr(
                                    "disabled",
                                    "$_sending || ($text.trim() === '' && $shots.length === 0)",
                                ),
                                SEND_ICON,
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
                h.Button(
                    {"type": "button", "class": "scrim", "aria-label": "Back to the app"},
                    data.show("$_history !== ''"),
                    data.on("click", "$_history = ''"),
                ),
            ),
            h.Div(
                {"id": "ink", "class": "ink"},
                data.ignore_morph(),
                data.init("app.ink.mount(el)"),
                h.Canvas({"class": "inkcanvas"}),
                h.Div(
                    {"class": "glass inktools"},
                    *[
                        h.Button(
                            {"type": "button", "data-tool": tool},
                            data.on("click", f"app.ink.tool('{tool}')"),
                            label,
                        )
                        for tool, label in (
                            ("marker", "Draw"),
                            ("arrow", "Arrow"),
                            ("ring", "Circle"),
                            ("box", "Box"),
                            ("text", "Text"),
                        )
                    ],
                    h.Button({"type": "button"}, data.on("click", "app.ink.undo()"), "Undo"),
                    h.Button({"type": "button"}, data.on("click", "app.ink.cancel()"), "Cancel"),
                    h.Button(
                        {"type": "button", "class": "done"},
                        data.on("click", "app.ink.done()"),
                        "Done",
                    ),
                ),
            ),
        ),
    )
