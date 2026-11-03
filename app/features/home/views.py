from stario import h
from stario.datastar import at, data
from stario.datastar.format import string_literal
from stario.markup import HtmlElement

from app.common.palette import accent
from app.common.shell import INK_LOOP, page
from app.features.auth.urls import LOGOUT
from app.features.frame.urls import FRAME
from app.features.home.urls import HOME_LIVE, NEW_APP

# A few things people build, to start from when the page is blank.
IDEAS = (
    (
        "Meal planner",
        "meals",
        "A weekly meal planner: pick a dinner for each day, and get one shopping list.",
    ),
    (
        "Habit tracker",
        "habits",
        "A habit tracker: a few daily habits I tick off, with a streak for each.",
    ),
    (
        "Shopping list",
        "shopping",
        "A shared shopping list my family can add to, and tick off in the shop.",
    ),
    (
        "Chore chart",
        "chores",
        "A chore chart for the family: who does what this week, ticked off when it is done.",
    ),
    (
        "Booking page",
        "booking",
        "A booking page for my small studio: people pick a free slot and leave their name.",
    ),
    (
        "Recipe box",
        "recipes",
        "A recipe box: save recipes with their ingredients and steps, and search them.",
    ),
)


def render(
    configured: tuple[tuple[str, str], ...],
    made: list[tuple],
    domain: str,
    can_make: bool,
    colors: dict[str, str],
) -> HtmlElement:
    return page(
        "nudgethis",
        h.Main(
            {"id": "home"},
            data.signals({"new_name": "", "new_from": "", "new_about": ""}, if_missing=True),
            data.init(at.get(HOME_LIVE.href(), retry="always")),
            h.H1("nudge", h.Span({"class": "this"}, "this")),
            h.Form(
                {"class": "sticker newapp"},
                data.on(
                    "submit",
                    at.post(NEW_APP.href(), include=["new_name", "new_from", "new_about"]),
                    prevent=True,
                ),
                data.indicator("_making"),
                h.Textarea(
                    {
                        "class": "newabout",
                        "rows": "2",
                        "maxlength": 2000,
                        "placeholder": "Describe your app: what should it do, and for whom?",
                        "aria-label": "what the new app should do",
                    },
                    data.bind("new_about"),
                )
                if can_make
                else None,
                h.Div(
                    {"class": "ideas", "role": "group", "aria-label": "ideas"},
                    *[
                        h.Button(
                            {"type": "button", "class": "chip"},
                            data.on(
                                "click",
                                f"$new_about = {string_literal(about)};"
                                f" $new_name = $new_name || {string_literal(slug)}",
                            ),
                            label,
                        )
                        for label, slug, about in IDEAS
                    ],
                )
                if can_make
                else None,
                h.Label(
                    {"class": "newname"},
                    h.Span({"class": "dim"}, "https://"),
                    h.Input(
                        {
                            "placeholder": "plants",
                            "maxlength": 30,
                            "required": True,
                            "autocomplete": "off",
                            "aria-label": "name of the new app",
                        },
                        data.bind("new_name"),
                    ),
                    h.Span({"class": "dim"}, f".{domain}"),
                ),
                h.Button(
                    {"type": "submit", "class": "make"},
                    data.attr("disabled", "$_making || !$new_name.trim()"),
                    "New app",
                )
                if can_make
                else h.Span({"class": "dim"}, "Set YARD_TOKEN to make apps."),
                h.Label(
                    {"class": "newfrom"},
                    h.Span({"class": "dim"}, "Start from"),
                    h.Input(
                        {
                            "type": "url",
                            "placeholder": "nudge-template, or a public GitHub repo",
                            "maxlength": 200,
                            "autocomplete": "off",
                            "aria-label": "a public GitHub repo to start from",
                        },
                        data.bind("new_from"),
                    ),
                )
                if can_make
                else None,
            ),
            h.Ul(
                {"class": "apps"},
                *[
                    h.Li(
                        {"style": f"--dot: {accent(colors.get(name, ''))}"},
                        h.A({"href": FRAME.href(name)}, name.removeprefix("nudge-"))
                        if status == "ready"
                        else h.Span({"class": "name"}, name.removeprefix("nudge-")),
                        h.Span({"class": "appurl"}, url),
                        h.Span({"class": f"state {status}"}, INK_LOOP, step)
                        if status == "creating"
                        else h.Span({"class": f"state {status}"}, step)
                        if status == "failed"
                        else None,
                    )
                    for name, url, status, step in made
                ],
                *[
                    h.Li(
                        {"style": f"--dot: {accent(colors.get(name, ''))}"},
                        h.A({"href": FRAME.href(name)}, name),
                        h.Span({"class": "appurl"}, url),
                    )
                    for name, url in configured
                ],
            ),
            h.Button(
                {"type": "button", "class": "logout"},
                data.on("click", at.post(LOGOUT.href())),
                "Sign out",
            ),
        ),
    )
