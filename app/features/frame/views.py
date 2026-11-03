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
from app.features.settings.urls import SETTINGS
from app.features.shots.urls import SHOT

STATUS_LABELS = {
    "working": "In progress",
    "deploying": "Going live",
    "live": "Done",
    "undone": "Undone",
    "dropped": "Didn't work",
}
# The chat's one status line while work goes on, by what is happening.
DOING = {
    "thinking": "Thinking…",
    "working": "Making the change…",
    "deploying": "Putting it live…",
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


def clip(text: str | None, most: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= most else text[: most - 1].rsplit(" ", 1)[0] + "…"


def when_text(stamp: str | None) -> HtmlElement | str:
    """The day and the hour, as a person says it. The server's is UTC; the
    browser rewrites it in the viewer's own time zone (app.frame.times)."""
    if not stamp:
        return ""
    at = datetime.fromisoformat(stamp)
    return h.Time({"datetime": stamp}, at.strftime("%-d %b, %H:%M"))


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


def message_li(m: Message, current: str) -> HtmlElement | None:
    tag = h.Span({"class": "tag"}, m.app) if m.app != current else None
    if m.thinking:
        return None  # the status line at the end of the chat says it
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
    # The chat only tells; the change's details and its Undo are in the Timeline.
    return h.Li(
        {"class": "msg nudge"},
        tag,
        h.Div({"class": "md"}, *markdown.render(m.text)),
        h.Button(
            {"type": "button", "class": "details"},
            data.on("click", f"$_view = 'changes'; app.frame.show('step-{m.change_id}')"),
            "Details",
        )
        # A change's outcome (live, or it did not work), not Nudge's "On it."
        if m.change_id and ("details" in m.actions or "undo" in m.actions)
        else None,
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


def composer(name: str) -> HtmlElement:
    """The one message form, at the foot of the sheet. The pencil draws on the app."""
    return h.Form(
        {"id": "composer", "class": "composer"},
        data.on(
            "submit",
            "app.dictate.stop(); " + at.post(SAY.href(name), include=["tab", "text", "shots"]),
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
                        {"type": "button", "class": "unshot", "aria-label": "Remove"},
                        data.on("click", f"$shots = $shots.filter((s, j) => j !== {i})"),
                        "×",
                    ),
                )
                for i in range(2)
            ],
        ),
        h.Div(
            {"class": "composerow"},
            h.Button(
                {"type": "button", "class": "round snap", "aria-label": "Draw on the app"},
                data.on("click", "app.snap.go(h => $_hint = h)"),
                data.attr("disabled", "$_sending"),
                DRAW_ICON,
            ),
            h.Textarea(
                {
                    "rows": "1",
                    "maxlength": 2000,
                    "placeholder": "Say what to change…",
                    "aria-label": "message",
                },
                data.bind("text"),
                data.ref("_box"),
                data.effect(
                    "$_sheet && $_view === 'chat'"
                    " && setTimeout(() => el.focus({preventScroll: true}), 80)"
                ),
                data.on(
                    "keydown",
                    "evt.key === 'Enter' && !evt.shiftKey"
                    " && (evt.preventDefault(), el.form.requestSubmit())",
                ),
            ),
            h.Button(
                {"type": "button", "class": "round mic", "aria-label": "Dictate"},
                data.show("app.dictate.can()"),
                data.class_("on", "$_listening"),
                data.attr("aria-pressed", "$_listening"),
                data.on("click", "app.dictate.toggle($_box, v => $_listening = v)"),
                MIC_ICON,
            ),
            h.Button(
                {"type": "submit", "class": "round send", "aria-label": "Send"},
                data.attr("disabled", "$_sending || ($text.trim() === '' && $shots.length === 0)"),
                SEND_ICON,
            ),
        ),
        h.Input(
            {"type": "file", "accept": "image/*", "hidden": True},
            data.init("app.snap.input(el)"),
            data.on("change", "app.snap.pick(evt); $_hint = ''"),
        ),
    )


MIC_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Rect({"x": "9", "y": "3", "width": "6", "height": "11", "rx": "3"}),
    svg.Path({"d": "M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"}),
)
HOME_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Path({"d": "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"}),
)
MORE_ICON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon", "aria-hidden": "true"},
    svg.Circle({"cx": "5", "cy": "12", "r": "1.4"}),
    svg.Circle({"cx": "12", "cy": "12", "r": "1.4"}),
    svg.Circle({"cx": "19", "cy": "12", "r": "1.4"}),
)
CHEVRON = svg.Svg(
    {"viewBox": "0 0 24 24", "class": "icon chev", "aria-hidden": "true"},
    svg.Path({"d": "M7 10l5 5 5-5"}),
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
    """The coder's settings, in the sheet's menu: which model, with which params."""
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
    # One dim line at the end of the chat while Nudge or the coder works, with
    # a clock from when that step began.
    thinking = next((m for m in here if m.thinking), None)
    active = next((row for row in timeline if row[2] in ("working", "deploying")), None)
    if thinking:
        doing, since = DOING["thinking"], thinking.at
    elif active:
        doing, since = DOING[active[2]], active[3] or ""
    else:
        doing, since = "", ""
    latest_id = pulse.latest.get(name, 0)
    unread = f"$_seen < {latest_id}"
    seen_key = string_literal(f"seen.{name}")
    in_flight = [row for row in reversed(timeline) if row[2] in ("working", "deploying")]
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
                    "color": color,
                    "snap": "",
                    "_rev": rev,
                    "_seen": 0,
                    "_sheet": False,
                    "_view": "chat",
                    "_apps": False,
                    "_menu": False,
                    "_hint": "",
                    "_inkwait": False,
                    "_listening": False,
                },
                if_missing=True,
            ),
            data.init(at.get(FRAME_LIVE.href(name), retry="always")),
            data.effect("app.frame.rev($_rev)"),
            data.on("pagehide", "app.snap.stop()", target="window"),
            # Esc closes a dropdown, then the sheet; / opens the sheet.
            data.on(
                "keydown",
                "evt.key === 'Escape' && ($_apps || $_menu"
                " ? ($_apps = false, $_menu = false) : ($_sheet = false));"
                " evt.key === '/' && !$_sheet && !evt.target.closest('input, textarea, select')"
                " && (evt.preventDefault(), $_sheet = true, $_view = 'chat')",
                target="window",
            ),
            # The app's colour: every accent on the page follows it.
            h.Style(f"#frame {{ --accent: {accent(color)}; }}"),
            h.Div(
                {"class": "stage"},
                data.class_("away", "$_sheet"),
                h.Iframe(
                    {"id": "app-frame", "src": url, "title": name},
                    data.ignore_morph(),
                    data.init("app.frame.bind(el); app.snap.bind(el)"),
                ),
                # The only thing over the app: tap to talk, hold to draw.
                h.Div(
                    {"id": "nudge", "data-latest": latest_id},
                    data.init(f"$_seen = app.pill.load({seen_key}, 0)"),
                    data.effect(f"app.pill.save({seen_key}, $_seen)"),
                    data.on(
                        "pill-tap",
                        "$_sheet = true; $_view = 'chat'; $_apps = false; $_menu = false",
                    ),
                    data.on("pill-hold", "app.snap.go(h => ($_hint = h, $_sheet = true))"),
                    h.Button(
                        {
                            "type": "button",
                            "class": "sticker pill",
                            "data-state": state,
                            "aria-label": "Nudge: tap to talk, hold to draw on the app",
                        },
                        data.preserve_attr(["style", "class"]),
                        data.show("!$_sheet"),
                        data.init("app.pill.mount(el)"),
                        h.Span({"class": "orb"}, data.class_("unread", unread)),
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
                ),
            ),
            h.Button(
                {"type": "button", "class": "scrim", "aria-label": "Back to the app"},
                data.show("$_sheet"),
                data.on("click", "$_sheet = false"),
            ),
            # The sheet: everything about the app, in one place.
            h.Aside(
                {"id": "sheet", "aria-label": "Nudge"},
                data.class_("open", "$_sheet"),
                data.init("app.swipe.mount(el); app.frame.times(el)"),
                data.on("swipe-close", "$_sheet = false"),
                # Reading the chat reads its replies: the orb goes grey.
                data.effect(
                    f"$_sheet && $_view === 'chat' && ($_seen = Math.max($_seen, {latest_id}))"
                ),
                h.Header(
                    {"class": "sheethead", "data-grab": True},
                    h.Span({"class": "grab", "aria-hidden": "true"}),
                    # Back to every app, and to making a new one: always one tap away.
                    h.A(
                        {"href": HOME.href(), "class": "round home", "aria-label": "All apps"},
                        HOME_ICON,
                    ),
                    h.Button(
                        {"type": "button", "class": "appswitch", "aria-label": "Switch app"},
                        data.on("click", "$_apps = !$_apps; $_menu = false"),
                        data.attr("aria-expanded", "$_apps"),
                        h.Span({"class": "dot", "aria-hidden": "true"}),
                        h.Span({"class": "appname"}, name.removeprefix("nudge-")),
                        CHEVRON,
                    ),
                    h.Button(
                        {"type": "button", "class": "round", "aria-label": "Settings"},
                        data.on("click", "$_menu = !$_menu; $_apps = false"),
                        data.attr("aria-expanded", "$_menu"),
                        MORE_ICON,
                    ),
                    h.Button(
                        {"type": "button", "class": "round close", "aria-label": "Back to the app"},
                        data.on("click", "$_sheet = false"),
                        CLOSE_ICON,
                    ),
                ),
                h.Div(
                    {"id": "apps", "class": "drop"},
                    data.show("$_apps"),
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
                    h.A({"href": HOME.href(), "class": "newlink"}, "All apps · New app"),
                ),
                h.Div(
                    {"id": "menu", "class": "drop"},
                    data.show("$_menu"),
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
                    coder,
                    h.A({"href": SETTINGS.href(), "class": "newlink"}, "All settings"),
                ),
                h.Div(
                    {"class": "tabs", "role": "tablist"},
                    *[
                        h.Button(
                            {"type": "button", "role": "tab"},
                            data.class_("on", f"$_view === '{key}'"),
                            data.attr("aria-selected", f"$_view === '{key}'"),
                            data.on("click", f"$_view = '{key}'"),
                            label,
                        )
                        for key, label in (("chat", "Chat"), ("changes", "Changes"))
                    ],
                ),
                # What is being worked on now, one plain line each.
                h.Ul(
                    {"class": "inflight", "aria-label": "in progress"},
                    data.show("$_view === 'chat'"),
                    *[
                        h.Li(
                            h.Span({"class": "what"}, clip(row[11] or row[9] or row[1], 70)),
                            h.Span(
                                {"class": "phase"},
                                "going live" if row[2] == "deploying" else "in progress",
                            ),
                        )
                        for row in in_flight
                    ],
                )
                if in_flight
                else None,
                h.Ol(
                    {"id": "msgs"},
                    data.show("$_view === 'chat'"),
                    data.init("el.pod ??= app.pod(el)"),
                    *(
                        [message_li(m, name) for m in here]
                        or [
                            h.Li(
                                {"class": "empty"},
                                "Tell me what to change in the app. Hold the pill to draw on it.",
                            )
                        ]
                    ),
                    h.Li(
                        {"class": "doing", "role": "status", "data-since": since},
                        data.init("app.frame.tick(el)"),
                        INK_LOOP,
                        h.Span(doing),
                        h.Span({"class": "clock"}),
                    )
                    if doing
                    else None,
                ),
                h.Ol(
                    {"class": "timeline"},
                    data.show("$_view === 'changes'"),
                    *(
                        [
                            h.Li(
                                {"class": f"step {status}", "id": f"step-{cid}"},
                                h.Span(
                                    {"class": "status"},
                                    STATUS_LABELS.get(status, status),
                                    h.Span({"class": "when"}, when_text(updated)),
                                ),
                                # Nudge's short title, else the person's own words; the
                                # coder's brief is for the coder.
                                h.P({"class": "brief"}, clip(title or request or brief, 140)),
                                h.P({"class": "result"}, clip(result, 280))
                                if result and status in ("live", "undone", "dropped")
                                else None,
                                h.Span({"class": "took"}, spent)
                                if (spent := took(asked, created, pushed, live))
                                else None,
                                undo_button(cid, name) if status == "live" else None,
                            )
                            for (
                                cid,
                                brief,
                                status,
                                updated,
                                asked,
                                created,
                                _,
                                pushed,
                                live,
                                request,
                                result,
                                title,
                            ) in timeline
                        ]
                        or [h.Li({"class": "empty"}, "No changes yet.")]
                    ),
                ),
                composer(name),
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
                        "!$_inkwait && ($shots = app.ink.take(), $snap = app.ink.got,"
                        " $_sheet = true, $_view = 'chat', "
                        + at.post(SAY.href(name), include=["tab", "text", "shots", "snap"])
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
