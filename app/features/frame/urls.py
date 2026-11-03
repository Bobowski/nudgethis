from stario import Route

FRAME = Route("GET /a/{app}")
FRAME_LIVE = Route("GET /a/{app}/live")
SAY = Route("POST /a/{app}/say")
UNDO = Route("POST /a/{app}/undo")
CODER = Route("POST /a/{app}/coder")
CODER_LIVE = Route("GET /a/{app}/coder/live")
COLOR = Route("POST /a/{app}/color")
