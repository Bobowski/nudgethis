from stario import h
from stario.datastar import at, data
from stario.datastar.format import string_literal
from stario.markup import HtmlElement

from app.common.palette import accent
from app.common.shell import INK_LOOP, page
from app.features.auth.urls import LOGOUT
from app.features.frame.urls import FRAME
from app.features.home.urls import HOME_LIVE, NEW_APP, REMOVE_APP, SUGGEST
from app.features.settings.urls import SETTINGS

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
            data.signals(
                {"new_name": "", "new_about": "", "remove_name": "", "_hint": "", "_from": ""},
                if_missing=True,
            ),
            data.init(at.get(HOME_LIVE.href(), retry="always")),
            h.Header(
                {"class": "homehead"},
                h.H1("nudge", h.Span({"class": "this"}, "this")),
                h.Nav(
                    h.A({"href": SETTINGS.href(), "class": "chip"}, "Settings"),
                    h.Button(
                        {"type": "button", "class": "chip logout"},
                        data.on("click", at.post(LOGOUT.href())),
                        "Sign out",
                    ),
                ),
            ),
            # One prompt: what to make. The name and the starting point follow from it.
            h.Form(
                {"class": "sticker newapp"},
                data.on(
                    "submit",
                    at.post(NEW_APP.href(), include=["new_name", "new_about"]),
                    prevent=True,
                ),
                data.indicator("_making"),
                h.Textarea(
                    {
                        "class": "prompt",
                        "rows": "3",
                        "maxlength": 2000,
                        "placeholder": "What do you want to make?",
                        "aria-label": "what the new app should do",
                    },
                    data.bind("new_about"),
                    data.on(
                        "input",
                        at.get(SUGGEST.href(), include=["new_about"]),
                        debounce="300ms",
                    ),
                    data.on(
                        "keydown",
                        "evt.key === 'Enter' && (evt.metaKey || evt.ctrlKey)"
                        " && (evt.preventDefault(), el.form.requestSubmit())",
                    ),
                ),
                h.Div(
                    {"class": "newfoot"},
                    # The app's own name, which is its address. Type one, or keep the
                    # one suggested from the prompt (shown greyed out).
                    h.Label(
                        {"class": "where"},
                        h.Span({"class": "what"}, "Address"),
                        h.Span(
                            {"class": "addr"},
                            h.Input(
                                {
                                    "class": "label",
                                    "maxlength": 30,
                                    "autocomplete": "off",
                                    "autocapitalize": "off",
                                    "spellcheck": "false",
                                    "aria-label": "the app's name, in its address",
                                },
                                data.bind("new_name"),
                                data.attr("placeholder", "$_hint || 'your-app'"),
                            ),
                            h.Span({"class": "dim"}, f".{domain}"),
                        ),
                    ),
                    h.Span(
                        {"class": "from dim"},
                        data.text("$_from ? 'from ' + $_from : 'from the nudge template'"),
                    ),
                    h.Button(
                        {"type": "submit", "class": "make"},
                        data.attr("disabled", "$_making || !$new_about.trim()"),
                        "Make it",
                    ),
                )
                if can_make
                else h.P({"class": "dim newfoot"}, "Set YARD_TOKEN to make apps."),
            ),
            h.Ul(
                {"class": "ideas", "aria-label": "ideas"},
                *[
                    h.Li(
                        h.Button(
                            {"type": "button"},
                            data.on(
                                "click",
                                f"$new_about = {string_literal(about)}; $new_name = ''; "
                                + at.get(SUGGEST.href(), include=["new_about"]),
                            ),
                            h.Strong(label),
                            h.Span(about),
                        )
                    )
                    for label, _, about in IDEAS
                ],
            )
            if can_make
            else None,
            h.H2("Your apps") if made or configured else None,
            h.Ul(
                {"class": "apps"},
                *[
                    h.Li(
                        {"style": f"--dot: {accent(colors.get(name, ''))}"},
                        h.A({"href": FRAME.href(name)}, name.removeprefix("nudge-"))
                        if status == "ready"
                        else h.Span({"class": "name"}, name.removeprefix("nudge-")),
                        h.Span({"class": f"state {status}"}, INK_LOOP, step)
                        if status == "creating"
                        else h.Span({"class": f"state {status}"}, "Didn't start: ", step)
                        if status == "failed"
                        else h.Span({"class": "appurl"}, url.removeprefix("https://")),
                        h.Button(
                            {
                                "type": "button",
                                "class": "remove",
                                "aria-label": f"Remove {name.removeprefix('nudge-')}",
                                "title": "Remove",
                            },
                            data.on(
                                "click",
                                f"$remove_name = {string_literal(name)}; $_remove.showModal()",
                            ),
                            "×",
                        )
                        if status != "creating"
                        else None,
                    )
                    for name, url, status, step in made
                ],
                *[
                    h.Li(
                        {"style": f"--dot: {accent(colors.get(name, ''))}"},
                        h.A({"href": FRAME.href(name)}, name),
                        h.Span({"class": "appurl"}, url.removeprefix("https://")),
                    )
                    for name, url in configured
                ],
            ),
            # Asks once before an app leaves the list.
            h.Dialog(
                {"class": "sticker confirm"},
                data.ref("_remove"),
                data.preserve_attr("open"),
                h.P(
                    h.Strong(
                        "Remove ", h.Span(data.text("$remove_name.replace('nudge-', '')")), "?"
                    ),
                ),
                h.P(
                    {"class": "dim"},
                    "Its chat and its history leave nudgethis. Its code and its site stay.",
                ),
                h.Div(
                    {"class": "row"},
                    h.Button(
                        {"type": "button", "class": "chip"},
                        data.on("click", "$_remove.close()"),
                        "Keep it",
                    ),
                    h.Button(
                        {"type": "button", "class": "chip danger"},
                        data.on(
                            "click",
                            "$_remove.close(); "
                            + at.post(REMOVE_APP.href(), include=["remove_name"]),
                        ),
                        "Remove",
                    ),
                ),
            ),
        ),
    )
