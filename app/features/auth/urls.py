from stario import Route

LOGIN = Route("GET /auth")
LOGIN_START = Route("POST /auth/{provider}")
# The provider sends the browser back here: /auth/google/callback is registered at Google.
LOGIN_CALLBACK = Route("GET /auth/{provider}/callback")
LOGOUT = Route("POST /auth/logout")
