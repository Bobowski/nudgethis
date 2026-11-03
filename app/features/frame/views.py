from datetime import datetime

from stario import h
from stario.datastar import at, data
from stario.datastar.format import string_literal
from stario.markup import HtmlElement, svg

from app.coder.cursor import Model
from app.common import markdown
from app.common.palette import COLORS, DEFAULT, accent
from app.common.shell import INK_LOOP, page
from app.features.frame.data import Message, Pulse
from app.features.frame.urls import CODER, CODER_LIVE, COLOR, FRAME, FRAME_LIVE, SAY, UNDO
from app.features.home.urls import HOME
from app.features.shots.urls import SHOT

STATUS_LABELS = {
    "working": "Working",
    "deploying": "Deploying",
    "live": "Live",
    "undone": "Undone",
    "dropped": "Failed",
}


DRAW_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Path({"d": "M4 20l4-1 10.5-10.5-3-3L5 16zM14 7l3 3"}),
)

CLOSE_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Path({"d": "M7 7l10 10M17 7 7 17"}),
)


def icon(d: str) -> HtmlElement:
    return svg.Svg(
        {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"}, svg.Path({"d": d})
    )


INK_TOOLS = (
    ("marker", "Draw", icon("M4 20l4-1 10.5-10.5-3-3L5 16zM14 7l3 3")),
    ("arrow", "Arrow", icon("M5 19 19 5M10 5h9v9")),
    ("ring", "Circle", icon("M12 4.5a7.5 7.5 0 1 0 0 15 7.5 7.5 0 1 0 0-15")),
    ("box", "Box", icon("M4.5 6.5h15v11h-15z")),
    ("text", "Text", icon("M6 6.5h12M12 6.5V19")),
)
UNDO_ICON = icon("M9 14 4 9l5-5M4 9h10.5a5.5 5.5 0 0 1 0 11H11")

SEND_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Path({"d": "M12 19V5M6 11l6-6 6 6"}),
)


def span_text(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 60:
        return f"{seconds} s"
    return f"{seconds // 60} min {seconds % 60} s" if seconds % 60 else f"{seconds // 60} min"


def took(asked: str | None, created: str | None, pushed: str | None, live: str | None) -> str:
    """How long a live change took, and where the time went, in plain words."""
    if not (live and created):
        return ""
    at = {
        k: datetime.fromisoformat(v)
        for k, v in (("asked", asked), ("created", created), ("pushed", pushed), ("live", live))
        if v
    }
    parts = []
    if "asked" in at:
        parts.append(f"Nudge {span_text((at['created'] - at['asked']).total_seconds())}")
    done = at.get("pushed", at["live"])
    parts.append(f"coding {span_text((done - at['created']).total_seconds())}")
    if "pushed" in at:
        parts.append(f"going live {span_text((at['live'] - at['pushed']).total_seconds())}")
    total = (at["live"] - at.get("asked", at["created"])).total_seconds()
    return f"Took {span_text(total)}: " + ", ".join(parts)


def undo_button(change_id: int, current: str) -> HtmlElement:
    return h.Button(
        {"type": "button", "class": "act undo"},
        data.on(
            "click",
            f"$change_id = {change_id}; "
            + at.post(UNDO.href(current), include=["tab", "change_id"]),
        ),
        "Undo",
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
        h.Div({"class": "md"}, *markdown.render(m.text)),
        undo_button(m.change_id, current) if "undo" in m.actions and m.change_id else None,
    )


def app_li(name: str, here: bool, color: str, phase: str, latest: int) -> HtmlElement:
    """One app in the apps panel: its colour, what its coder does, and a new reply."""
    seen = string_literal(f"seen.{name}")
    return h.Li(
        {"class": "appitem here" if here else "appitem", "style": f"--dot: {accent(color)}"},
        h.A(
            {"href": FRAME.href(name)},
            data.on("click", "$_apps = false") if here else None,
            h.Span({"class": "dot", "aria-hidden": "true"}),
            h.Span({"class": "name"}, name.removeprefix("nudge-")),
            h.Span({"class": "state"}, INK_LOOP, "Deploying" if phase == "deploying" else "Working")
            if phase
            else None,
            h.Span(
                {"class": "new", "aria-label": "new reply"},
                data.show(f"$_seen < {latest}" if here else f"app.pill.load({seen}, 0) < {latest}"),
            )
            if latest
            else None,
        ),
    )


def composer(name: str, docked: bool) -> HtmlElement:
    """The message form. Docked, it opens out of the pill; in the panel, it stays open.
    Replies show only in the panel's chat."""
    return h.Form(
        {"id": "composer" if docked else "chatbox", "class": "sticker card composer"},
        data.show("$_compose") if docked else None,
        data.on(
            "submit",
            at.post(SAY.href(name), include=["tab", "text", "shots"])
            + ("; $_compose = false" if docked else ""),
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
                {"type": "button", "class": "round close", "aria-label": "Close"},
                data.on("click", "$_compose = false"),
                CLOSE_ICON,
            )
            if docked
            else None,
            h.Button(
                {"type": "button", "class": "round snap", "aria-label": "Draw on the app"},
                data.on(
                    "click",
                    "app.snap.go(h => $_hint = h)",
                ),
                data.attr("disabled", "$_sending"),
                DRAW_ICON,
            ),
            h.Textarea(
                {
                    "rows": "1",
                    "maxlength": 2000,
                    "placeholder": "Say what you want…",
                    "aria-label": "message",
                },
                data.bind("text"),
                data.effect("$_compose && setTimeout(() => el.focus({preventScroll: true}), 60)")
                if docked
                else None,
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
                "app.snap.pick(evt); $_hint = ''",
            ),
        )
        if docked
        else None,
    )


VENDORS = (
    ("Cursor", ("default", "composer")),
    ("xAI", ("grok",)),
    ("Anthropic", ("claude",)),
    ("OpenAI", ("gpt",)),
    ("Google", ("gemini",)),
)


def coder_panel(
    name: str, models: tuple[Model, ...], model_id: str, params: dict[str, str], live: bool
) -> HtmlElement:
    """The Coder tab: where each change runs, on which model, with which params."""
    model = next((m for m in models if m.id == model_id), None)
    post = at.post(CODER.href(name), include=["tab", "coder_set"])

    def group(prefixes: tuple[str, ...] | None) -> list[Model]:
        known = tuple(p for _, ps in VENDORS for p in ps)
        return [
            m
            for m in models
            if (m.id.startswith(prefixes) if prefixes else not m.id.startswith(known))
        ]

    return h.Div(
        {"id": "coder", "class": "coder"},
        data.show("$_history === 'coder'"),
        data.init(at.get(CODER_LIVE.href(name), retry="always")),
        h.P(
            {"class": "lead"},
            "Each change runs on a Cursor Cloud Agent, which pushes to main."
            if live
            else "The coder is fake. Set CURSOR_API_KEY to run on Cursor.",
        ),
        h.Label(
            {"class": "setting"},
            h.Span({"class": "name"}, "Model"),
            h.Select(
                {"class": "picker", "aria-label": "model"},
                data.on("change", "$coder_set = 'model=' + el.value; " + post),
                *[
                    h.Optgroup(
                        {"label": vendor},
                        *[
                            h.Option(
                                {"value": m.id, **({"selected": True} if m.id == model_id else {})},
                                m.label,
                            )
                            for m in members
                        ],
                    )
                    for vendor, members in [
                        *((v, group(ps)) for v, ps in VENDORS),
                        ("Other", group(None)),
                    ]
                    if members
                ],
            ),
        )
        if live and models
        else h.P({"class": "dim"}, f"Model: {model_id or 'Auto'}"),
        *[
            h.Div(
                {"class": "setting"},
                h.Span({"class": "name"}, p.label),
                h.Div(
                    {"class": "seg", "role": "group", "aria-label": p.label},
                    *[
                        h.Button(
                            {
                                "type": "button",
                                **({"class": "on"} if params.get(p.id) == v else {}),
                            },
                            data.on(
                                "click", f"$coder_set = {string_literal(f'{p.id}={v}')}; " + post
                            ),
                            label,
                        )
                        for v, label in p.values
                    ],
                ),
            )
            for p in (model.params if model and live else ())
        ],
        h.P({"class": "maxmode"}, "Max Mode: each run costs more.")
        if model and model.is_max(params)
        else None,
    )


def render(
    pulse: Pulse,
    name: str,
    url: str,
    timeline: list[tuple],
    rev: int,
    tab: str,
    coder: HtmlElement,
    names: list[str],
) -> HtmlElement:
    here = pulse.messages
    phase = pulse.phases.get(name, "")
    color = pulse.colors.get(name, DEFAULT)
    if any(m.thinking for m in here):
        state, label = "busy", "Thinking"
    elif phase:
        state, label = "busy", phase.capitalize()
    else:
        state, label = "idle", name
    active = next((row for row in timeline if row[2] in ("working", "deploying")), None)
    if any(m.thinking for m in here):
        doing = "Nudge is thinking."
    elif active:
        verb = "Deploying" if active[2] == "deploying" else "The coder is working on"
        doing = f"{verb} #{active[0]}: {active[1]}"
    else:
        doing = ""
    latest_id = pulse.latest.get(name, 0)
    unread = f"$_seen < {latest_id}"
    seen_key = string_literal(f"seen.{name}")
    return page(
        f"nudgethis · {name}",
        h.Div(
            {"id": "frame"},
            data.signals(
                {
                    "tab": tab,
                    "text": "",
                    "shots": [],
                    "change_id": 0,
                    "coder_set": "",
                    "_rev": rev,
                    "_dock": "top",
                    "_seen": 0,
                    "_compose": False,
                    "_history": "",
                    "_hint": "",
                    "_inkwait": False,
                    "_apps": False,
                    "color": color,
                },
                if_missing=True,
            ),
            data.init(at.get(FRAME_LIVE.href(name), retry="always")),
            data.effect("app.frame.rev($_rev)"),
            data.on("pagehide", "app.snap.stop()", target="window"),
            data.on(
                "keydown",
                "evt.key === 'Escape' && ($_compose = false, $_history = '', $_apps = false)",
                target="window",
            ),
            # The app's colour: every accent on the page follows it.
            h.Style(f"#frame {{ --accent: {accent(color)}; }}"),
            h.Aside(
                {"id": "apps"},
                data.class_("open", "$_apps"),
                data.init("app.swipe.mount(el)"),
                data.on("swipe-close", "$_apps = false"),
                h.Header(
                    {"class": "histhead"},
                    h.A({"href": HOME.href(), "class": "home"}, "‹ nudgethis"),
                    h.Span({"class": "appname"}, "Apps"),
                    h.Button(
                        {"type": "button", "class": "round close", "aria-label": "Back to the app"},
                        data.on("click", "$_apps = false"),
                        CLOSE_ICON,
                    ),
                ),
                h.Ul(
                    {"class": "applist"},
                    *[
                        app_li(
                            other,
                            other == name,
                            pulse.colors.get(other, DEFAULT),
                            pulse.phases.get(other, ""),
                            pulse.latest.get(other, 0),
                        )
                        for other in names
                    ],
                ),
                h.Div(
                    {"class": "swatches", "role": "group", "aria-label": f"colour of {name}"},
                    h.Span({"class": "name"}, "Colour"),
                    h.Div(
                        {"class": "row"},
                        *[
                            h.Button(
                                {
                                    "type": "button",
                                    "class": "swatch",
                                    "style": f"--sw: {value}",
                                    "aria-label": key,
                                    "title": key,
                                },
                                data.class_("on", f"$color === '{key}'"),
                                data.on(
                                    "click",
                                    f"$color = '{key}'; "
                                    + at.post(COLOR.href(name), include=["color"]),
                                ),
                            )
                            for key, value in COLORS.items()
                        ],
                    ),
                ),
            ),
            h.Aside(
                {"id": "history"},
                data.class_("open", "$_history !== ''"),
                data.init("app.swipe.mount(el)"),
                data.on("swipe-close", "$_history = ''"),
                h.Header(
                    {"class": "histhead"},
                    h.A({"href": HOME.href(), "class": "home"}, "‹ nudgethis"),
                    h.Span({"class": "appname"}, name),
                    h.Button(
                        {"type": "button", "class": "round close", "aria-label": "Back to the app"},
                        data.on("click", "$_history = ''"),
                        CLOSE_ICON,
                    ),
                ),
                h.Div(
                    {"class": "tabs", "role": "tablist"},
                    *[
                        h.Button(
                            {"type": "button", "role": "tab"},
                            data.class_("on", f"$_history === '{key}'"),
                            data.attr("aria-selected", f"$_history === '{key}'"),
                            data.on("click", f"$_history = '{key}'"),
                            label,
                        )
                        for key, label in (
                            ("chat", "Chat"),
                            ("timeline", "Timeline"),
                            ("coder", "Coder"),
                        )
                    ],
                ),
                h.P({"class": "statusline", "role": "status"}, INK_LOOP, doing) if doing else None,
                h.Ol(
                    {"id": "msgs"},
                    data.show("$_history === 'chat'"),
                    data.init("el.pod ??= app.pod(el)"),
                    *(
                        [message_li(m, name) for m in here]
                        or [
                            h.Li(
                                {"class": "empty"},
                                "Tap the pill to say what you want. Hold it to draw on the app.",
                            )
                        ]
                    ),
                ),
                h.Ol(
                    {"class": "timeline"},
                    data.show("$_history === 'timeline'"),
                    *(
                        [
                            h.Li(
                                {"class": f"step {status}"},
                                h.Span({"class": "when"}, (updated or "")[:16].replace("T", " ")),
                                h.P({"class": "brief"}, brief),
                                h.Span(
                                    {"class": "status"},
                                    f"#{cid} · {STATUS_LABELS.get(status, status)}",
                                ),
                                h.Span({"class": "took"}, spent)
                                if (spent := took(asked, created, pushed, live))
                                else None,
                                undo_button(cid, name) if status == "live" else None,
                            )
                            for cid, brief, status, updated, asked, created, _, pushed, live in (
                                timeline
                            )
                        ]
                        or [h.Li({"class": "empty"}, "No changes yet.")]
                    ),
                ),
                coder,
                h.Div(
                    {"class": "chatfoot"},
                    data.show("$_history === 'chat'"),
                    composer(name, docked=False),
                ),
            ),
            h.Div(
                {"class": "stage"},
                data.class_("away", "$_history !== ''"),
                data.class_("awayleft", "$_apps"),
                h.Iframe(
                    {"id": "app-frame", "src": url, "title": name},
                    data.ignore_morph(),
                    data.init("app.frame.bind(el); app.snap.bind(el)"),
                ),
                h.Div(
                    {
                        "id": "nudge",
                        "data-latest": latest_id,
                    },
                    data.class_("bottom", "$_dock === 'bottom'"),
                    data.init(
                        "$_dock = app.pill.load('dock', 'top');"
                        f" $_seen = app.pill.load({seen_key}, 0)"
                    ),
                    data.effect(
                        f"app.pill.save('dock', $_dock); app.pill.save({seen_key}, $_seen)"
                    ),
                    data.on("pill-dock", "$_dock = evt.detail"),
                    data.on("pill-pull", "$_compose = true"),
                    data.on(
                        "pill-swipe",
                        "evt.detail === 'left' ? ($_compose = false, $_apps = false,"
                        " $_history = 'chat', $_seen = +el.dataset.latest)"
                        " : ($_compose = false, $_history = '', $_apps = true)",
                    ),
                    data.on(
                        "pill-tap",
                        "$_compose = true",
                    ),
                    data.on(
                        "pill-hold",
                        "app.snap.go(h => ($_hint = h, $_compose = true))",
                    ),
                    data.on(
                        "blur",
                        "!$text.trim() && !$shots.length && ($_compose = false)",
                        target="window",
                    ),
                    h.Button(
                        {
                            "type": "button",
                            "class": "sticker pill",
                            "data-state": state,
                            "aria-label": "Nudge: tap, pull, swipe, or hold",
                        },
                        data.preserve_attr(["style", "class"]),
                        data.show("!$_compose"),
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
                        h.Span({"class": "label"}, label),
                        INK_LOOP if state == "busy" else None,
                    ),
                    composer(name, docked=True),
                ),
                h.Button(
                    {"type": "button", "class": "scrim", "aria-label": "Back to the app"},
                    data.show("$_history !== '' || $_apps"),
                    data.on("click", "$_history = ''; $_apps = false"),
                ),
            ),
            h.Div(
                {"id": "ink", "class": "ink"},
                data.ignore_morph(),
                data.init("app.ink.mount(el)"),
                data.on("ink-wait", "$_inkwait = evt.detail"),
                h.Div(
                    {"class": "inkstage"},
                    h.Canvas({"class": "inkcanvas"}),
                    h.Input(
                        {
                            "class": "inktext",
                            "hidden": True,
                            "maxlength": 80,
                            "placeholder": "Type…",
                            "aria-label": "text on the snap",
                        }
                    ),
                ),
                h.Form(
                    {"class": "sticker inkbar"},
                    data.on(
                        "submit",
                        "!$_inkwait && ($shots = app.ink.take(), $_compose = false, "
                        + at.post(SAY.href(name), include=["tab", "text", "shots"])
                        + ")",
                        prevent=True,
                    ),
                    data.indicator("_sending"),
                    h.Div(
                        {"class": "inktools"},
                        h.Button(
                            {"type": "button", "class": "round", "aria-label": "Cancel"},
                            data.on("click", "app.ink.cancel()"),
                            CLOSE_ICON,
                        ),
                        *[
                            h.Button(
                                {
                                    "type": "button",
                                    "class": "round",
                                    "data-tool": tool,
                                    "aria-label": label,
                                    "title": label,
                                },
                                data.on("click", f"app.ink.tool('{tool}')"),
                                glyph,
                            )
                            for tool, label, glyph in INK_TOOLS
                        ],
                        h.Button(
                            {
                                "type": "button",
                                "class": "round",
                                "aria-label": "Undo",
                                "title": "Undo",
                            },
                            data.on("click", "app.ink.undo()"),
                            UNDO_ICON,
                        ),
                    ),
                    h.Div(
                        {"class": "inkmsg"},
                        h.Textarea(
                            {
                                "rows": "1",
                                "maxlength": 2000,
                                "placeholder": "Say what to change…",
                                "aria-label": "message",
                            },
                            data.bind("text"),
                            data.on(
                                "keydown",
                                "evt.key === 'Enter' && !evt.shiftKey"
                                " && (evt.preventDefault(), el.form.requestSubmit())",
                            ),
                        ),
                        h.Button(
                            {"type": "submit", "class": "round send", "aria-label": "Send"},
                            data.attr("disabled", "$_sending || $_inkwait"),
                            SEND_ICON,
                        ),
                    ),
                ),
            ),
        ),
    )
