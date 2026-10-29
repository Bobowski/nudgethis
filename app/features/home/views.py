from stario import h
from stario.markup import HtmlElement

from app.common.shell import page
from app.features.frame.urls import FRAME


def render(apps: tuple[tuple[str, str], ...]) -> HtmlElement:
    return page(
        "nudgethis",
        h.Main(
            {"id": "home"},
            h.H1("nudgethis"),
            h.Ul(
                *[
                    h.Li(
                        h.A({"href": FRAME.href(name)}, name),
                        h.Span({"class": "appurl"}, url),
                    )
                    for name, url in apps
                ]
            )
            if apps
            else h.P("No apps configured. Set NUDGE_APPS."),
        ),
    )
