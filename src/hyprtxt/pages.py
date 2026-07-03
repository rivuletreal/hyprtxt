import io
import pathlib

from .core import STATIC, Content, Provider


class StaticProvider(Provider):
    def __init__(
        self,
        paths: dict[str, str | bytes | io.IOBase | pathlib.Path],
        priority: int = 100,
        _internal_default_replace: bool = False,
    ) -> None:
        self.paths = dict(
            [(k.removeprefix("/").removesuffix("/"), v) for k, v in paths.items()]
        )
        self.priority = priority
        self._internal_default_replace = _internal_default_replace

    def get_path(self, path: str) -> Content | None:
        is_catchall = False

        if (stripped := path.removeprefix("/").removesuffix("/")) in self.paths:
            content = self.paths[stripped]
        elif "*" in self.paths:
            content = self.paths["*"]
            is_catchall = True
        else:
            return None

        if isinstance(content, pathlib.Path):
            content = content.read_bytes()
        elif isinstance(content, io.IOBase):
            content = content.read()

        if self._internal_default_replace and is_catchall:
            if isinstance(content, str):
                content = content.replace("${noscript-err}", path)
            else:
                content = content.replace(b"${noscript-err}", path.encode())

        return Content(
            content,
            200,
            headers={
                "Content-Security-Policy": "default-src 'self' 'unsafe-inline'; connect-src 'self' wss: ws:"
            },
        )


_DEFAULT_STATIC_PROVIDER = StaticProvider(
    {
        "*": STATIC["default.html"],
        "/_hyprtxt/main.css": STATIC["main.css"],
        "/_hyprtxt/main.js": STATIC["main.js"],
    },
    0,
    _internal_default_replace=True,
)
