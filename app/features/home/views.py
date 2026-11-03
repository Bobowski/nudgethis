from stario import h
from stario.datastar import at, data
from stario.markup import HtmlElement

from app.common.shell import INK_LOOP, page
from app.features.auth.urls import LOGOUT
from app.features.frame.urls import FRAME
from app.features.home.urls import HOME_LIVE, NEW_APP


def render(
    configured: tuple[tuple[str, str], ...], made: list[tuple], domain: str, can_make: bool
) -> HtmlElement:
    return page(
        "nudgethis",
        h.Main(
            {"id": "home"},
            data.signals({"new_name": ""}, if_missing=True),
            data.init(at.get(HOME_LIVE.href(), retry="always")),
            h.H1("nudge", h.Span({"class": "this"}, "this")),
            h.Form(
                {"class": "sticker newapp"},
                data.on("submit", at.post(NEW_APP.href(), include=["new_name"]), prevent=True),
                data.indicator("_making"),
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
            ),
            h.Ul(
                {"class": "apps"},
                *[
                    h.Li(
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
