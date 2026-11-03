from datetime import datetime
from typing import cast

from stario import h
from stario.datastar import at, data
from stario.json import loads
from stario.markup import HtmlElement

from app.builder import SECRETS, Builder
from app.common.shell import page
from app.config import EFFORTS
from app.features.home.urls import HOME
from app.features.settings.urls import SAVE_SETTINGS

# Each section: its title, what it is for, and its fields (key, label, help).
SECTIONS = (
    (
        "Nudge",
        "The assistant you talk to. Any OpenAI-compatible provider works.",
        (
            ("openai_api_key", "API key", "From your provider (OpenAI by default)."),
            ("openai_base_url", "Provider address", "Empty for OpenAI; else its /v1 address."),
            ("model", "Model", "The model Nudge thinks with."),
            ("effort", "Effort", "How hard it thinks before it answers."),
        ),
    ),
    (
        "Coder",
        "The agent that changes an app's code: Cursor Cloud Agents.",
        (
            ("cursor_api_key", "Cursor API key", "From cursor.com, under Integrations."),
            ("cursor_model", "Default model", "Each app can pick its own in its sheet's menu."),
        ),
    ),
    (
        "Hosting",
        "Where the apps live: Yard makes their repos, runs them, and deploys each push.",
        (
            ("yard_token", "Yard token", "From yard token new."),
            ("yard_url", "Yard address", "How nudgethis reaches Yard."),
            ("domain", "Domain", "A new app lives at name.this-domain."),
            ("owner", "Repo owner", "The GitHub account of new repos, when Yard is on several."),
            ("template", "Template", "The repo a new app starts from."),
        ),
    ),
)


def tokens(n: int) -> str:
    return (
        f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else f"{n / 1000:.1f}k" if n >= 1000 else str(n)
    )


def size(n: float) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def minutes(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds >= 90 else f"{seconds:.0f} s"


def coder_seconds(times: str) -> float:
    """The coder's time on an app's changes: from its start to its push (or live)."""
    total = 0.0
    for ran, pushed, live in cast(list[list[str | None]], loads(times or "[]")):
        end = pushed or live
        if ran and end:
            total += (datetime.fromisoformat(end) - datetime.fromisoformat(ran)).total_seconds()
    return total


def render(
    builder: Builder,
    saved: set[str],
    usage: list[tuple],
    made: list[str],
    shots: dict[str, int],
    data_bytes: int,
) -> HtmlElement:
    config, base = builder.config, builder.base
    value = {
        "openai_api_key": config.openai_api_key,
        "openai_base_url": config.openai_base_url or "",
        "model": config.model,
        "effort": config.effort,
        "cursor_api_key": config.cursor_api_key,
        "cursor_model": ":".join(
            [config.cursor_model, ",".join(f"{k}={v}" for k, v in config.cursor_params)]
        ).rstrip(":"),
        "yard_token": config.yard_token,
        "yard_url": config.yard_url,
        "domain": config.domain,
        "owner": config.owner,
        "template": config.template,
    }
    from_env = {
        "openai_api_key": base.openai_api_key,
        "cursor_api_key": base.cursor_api_key,
        "yard_token": base.yard_token,
    }

    def source(key: str) -> str:
        if key in saved:
            return "saved here"
        if key in SECRETS:
            return "from the environment" if from_env[key] else "not set"
        return "default"

    def field(key: str, label: str, help_text: str) -> HtmlElement:
        signal = f"s_{key}"
        if key in SECRETS:
            current = value[key]
            control = h.Input(
                {
                    "type": "password",
                    "autocomplete": "off",
                    "placeholder": f"•••• {current[-4:]}" if current else "Paste it here",
                    "aria-label": label,
                },
                data.bind(signal),
            )
        elif key == "effort":
            control = h.Select(
                {"aria-label": label},
                data.bind(signal),
                *[
                    h.Option({"value": e, **({"selected": True} if e == value[key] else {})}, e)
                    for e in EFFORTS
                ],
            )
        elif key == "cursor_model" and builder.models:
            control = h.Select(
                {"aria-label": label},
                data.bind(signal),
                h.Option({"value": ""}, "Cursor's default"),
                *[
                    h.Option(
                        {
                            "value": m.id,
                            **({"selected": True} if m.id == config.cursor_model else {}),
                        },
                        m.label,
                    )
                    for m in builder.models
                ],
            )
        else:
            control = h.Input(
                {"autocomplete": "off", "spellcheck": "false", "aria-label": label},
                data.bind(signal),
            )
        return h.Label(
            {"class": "field"},
            h.Span(
                {"class": "label"}, label, h.Span({"class": f"src {source(key)[:5]}"}, source(key))
            ),
            control,
            h.Span({"class": "help"}, help_text),
            h.Button(
                {"type": "button", "class": "linkish"},
                data.on(
                    "click",
                    f"$clear = '{key}'; " + at.post(SAVE_SETTINGS.href(), include=["clear"]),
                ),
                "Use the environment's" if key in SECRETS else "Use the default",
            )
            if key in saved
            else None,
        )

    status = {
        "Nudge": f"Thinking with {builder.model_name}."
        if builder.model_name != "fake"
        else "No API key: Nudge is a stand-in that only echoes.",
        "Coder": (
            f"Connected: {len(builder.models)} models."
            if builder.cursor and builder.models
            else f"Cursor did not answer: {builder.models_error}"
            if builder.cursor and builder.models_error
            else "No key: changes are pretend."
        ),
        "Hosting": "Connected." if builder.yard else "No token: new apps cannot be made.",
    }
    healthy = {
        title
        for title, ok in (
            ("Nudge", builder.model_name != "fake"),
            ("Coder", bool(builder.cursor and builder.models)),
            ("Hosting", builder.yard is not None),
        )
        if ok
    }
    signals = {f"s_{key}": "" if key in SECRETS else value[key] for key in value}

    rows = []
    totals = {"in": 0, "out": 0, "live": 0, "undone": 0, "dropped": 0, "secs": 0.0, "shots": 0}
    for app, turns, t_in, t_out, live, undone, dropped, working, times, last, names in usage:
        secs = coder_seconds(times)
        shot_bytes = sum(shots.get(n, 0) for n in cast(list[str], loads(names or "[]")))
        for key, n in (
            ("in", t_in),
            ("out", t_out),
            ("live", live),
            ("undone", undone),
            ("dropped", dropped),
            ("secs", secs),
            ("shots", shot_bytes),
        ):
            totals[key] += n
        rows.append(
            h.Tr(
                h.Th({"scope": "row"}, app.removeprefix("nudge-")),
                h.Td(str(live), h.Span({"class": "dim"}, " · working") if working else None),
                h.Td(
                    f"{tokens(t_in + t_out)}",
                    h.Span({"class": "dim"}, f" · {turns} turn{'' if turns == 1 else 's'}"),
                ),
                h.Td(minutes(secs)),
                h.Td(size(shot_bytes)),
                h.Td({"class": "dim"}, (last or "")[:10]),
            )
        )

    return page(
        "nudgethis · settings",
        h.Main(
            {"id": "settings"},
            data.signals({**signals, "clear": ""}, if_missing=True),
            h.Header(
                {"class": "homehead"},
                h.A({"href": HOME.href(), "class": "back"}, "‹ Apps"),
                h.H1("Settings"),
            ),
            *[
                h.Form(
                    {"class": "section"},
                    data.on(
                        "submit",
                        "$clear = ''; "
                        + at.post(
                            SAVE_SETTINGS.href(),
                            include=[f"s_{key}" for key, _, _ in fields] + ["clear"],
                        ),
                        prevent=True,
                    ),
                    data.indicator("_saving"),
                    h.H2(title),
                    h.P({"class": "dim lead"}, lead),
                    h.P(
                        {"class": "state ok" if title in healthy else "state"},
                        status[title],
                    ),
                    *[field(*f) for f in fields],
                    h.Button(
                        {"type": "submit", "class": "save"},
                        data.attr("disabled", "$_saving"),
                        "Save",
                    ),
                )
                for title, lead, fields in SECTIONS
            ],
            h.Section(
                {"class": "section usage"},
                h.H2("Usage"),
                h.Div(
                    {"class": "totals"},
                    *[
                        h.Div(h.Strong(big), h.Span({"class": "dim"}, small))
                        for big, small in (
                            (tokens(totals["in"] + totals["out"]), "Nudge tokens"),
                            (str(totals["live"]), "changes live"),
                            (minutes(totals["secs"]), "coder time"),
                            (size(data_bytes), "data on disk"),
                        )
                    ],
                ),
                h.P(
                    {"class": "dim lead"},
                    f"{tokens(totals['in'])} tokens in, {tokens(totals['out'])} out."
                    f" {totals['undone']} changes undone, {totals['dropped']} did not work."
                    f" {len(made)} apps made here. Screenshots: {size(totals['shots'])}."
                    " Cursor's own credit is on cursor.com, under Usage.",
                ),
                h.Table(
                    h.Thead(
                        h.Tr(
                            *[
                                h.Th({"scope": "col"}, t)
                                for t in ("App", "Live", "Nudge", "Coder", "Shots", "Last")
                            ]
                        )
                    ),
                    h.Tbody(*rows),
                )
                if rows
                else h.P({"class": "dim"}, "Nothing yet."),
            ),
        ),
    )
