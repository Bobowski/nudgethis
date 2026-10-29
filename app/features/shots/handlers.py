import re
from dataclasses import dataclass
from pathlib import Path

from stario import App, Context, Writer

from app.features.shots.urls import SHOT

SHOT_NAME = re.compile(r"[0-9a-f]+\.(png|jpg|webp)")
CONTENT_TYPES = {
    ".png": b"image/png",
    ".jpg": b"image/jpeg",
    ".webp": b"image/webp",
}


@dataclass(frozen=True, slots=True)
class ShotsPage:
    shots_dir: Path

    def register(self, app: App) -> None:
        app.add(SHOT, self.show)

    async def show(self, c: Context, w: Writer) -> None:
        name = c.match.params["name"]
        path = self.shots_dir / name
        if not SHOT_NAME.fullmatch(name) or not path.is_file():
            w.text("no such shot", status=404)
            return
        w.respond(path.read_bytes(), CONTENT_TYPES[path.suffix])
