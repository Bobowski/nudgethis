from stario import h
from stario.markup import HtmlElement

from app.common.shell import page
from app.features.auth.urls import LOGIN_START

# The button text for each provider name in app/main.py.
LABELS = {"google": "Google", "github": "GitHub"}

ERRORS = {
    "denied": "The sign-in was cancelled.",
    "expired": "The sign-in did not finish. Try again.",
    "failed": "The sign-in did not work. Try again.",
    "not_allowed": "This account cannot use nudgethis. Pick another one.",
}


def render(providers: list[str], next_url: str, error: str) -> HtmlElement:
    message = ERRORS.get(error)
    return page(
        "nudgethis · sign in",
        h.Main(
            {"id": "home"},
            h.H1("nudgethis"),
            h.P({"role": "alert"}, message) if message else None,
            # Plain forms: the answer is a redirect to the provider.
            [
                h.Form(
                    {"method": "post", "action": LOGIN_START.href(name)},
                    h.Input({"type": "hidden", "name": "next", "value": next_url}),
                    h.Button({"type": "submit"}, f"Continue with {LABELS.get(name, name)}"),
                )
                for name in providers
            ],
        ),
    )
