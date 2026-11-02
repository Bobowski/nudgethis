import hmac
import secrets
from dataclasses import dataclass

from stario import App, Context, Writer
from stario.cookies import delete_cookie, set_cookie
from stario.datastar import SSE

from app.common.session import Session
from app.features.home.urls import HOME
from app.features.signin.urls import SIGNIN, SIGNIN_GOOGLE, SIGNOUT
from app.features.signin.views import render
from app.oauth.google import Google

STATE = "signin_state"


@dataclass(frozen=True, slots=True)
class SigninPage:
    session: Session
    google: Google
    allowed: frozenset[str]
    public_url: str

    def register(self, app: App) -> None:
        app.add(SIGNIN, self.show)
        app.add(SIGNIN_GOOGLE, self.back)
        app.add(SIGNOUT, self.signout)

    def redirect_uri(self) -> str:
        return self.public_url + SIGNIN_GOOGLE.href()

    async def show(self, c: Context, w: Writer) -> None:
        if c.state.get("user"):
            w.redirect(HOME.href(), status=303)
            return
        state = secrets.token_urlsafe(24)
        set_cookie(
            w,
            STATE,
            state,
            max_age=600,
            httponly=True,
            secure=self.session.secure,
            samesite="lax",
        )
        w.redirect(self.google.auth_url(self.redirect_uri(), state), status=303)

    async def back(self, c: Context, w: Writer) -> None:
        code = c.req.query.get("code", "")
        state = c.req.query.get("state", "")
        expected = c.req.cookies.get(STATE, "")
        if not code or not expected or not hmac.compare_digest(state, expected):
            w.text("the sign-in expired; start again", status=400)
            return
        email = await self.google.email(code, self.redirect_uri())
        delete_cookie(w, STATE, httponly=True, secure=self.session.secure, samesite="lax")
        if email is None:
            w.html(render("Google did not confirm the account."), status=403)
            return
        if email not in self.allowed:
            c.span.attr("signin.refused", email)
            w.html(render(f"{email} cannot use nudgethis."), status=403)
            return
        self.session.issue(w, email)
        w.redirect(HOME.href(), status=303)

    async def signout(self, c: Context, w: Writer) -> None:
        self.session.clear(w)
        SSE(w).navigate(SIGNIN.href())
