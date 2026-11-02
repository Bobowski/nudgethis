from stario import h
from stario.markup import HtmlElement

from app.common.shell import page
from app.features.auth.urls import AUTH_GOOGLE


def render(message: str) -> HtmlElement:
    return page(
        "nudgethis · sign in",
        h.Main(
            {"id": "home"},
            h.H1("nudgethis"),
            h.P(message),
            h.P(h.A({"href": AUTH_GOOGLE.href()}, "Sign in with another account")),
        ),
    )
