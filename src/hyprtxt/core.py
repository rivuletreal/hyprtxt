import asyncio
import dataclasses
import io
import json
import pathlib
import traceback
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import resources

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

pages: "dict[str, type[Page]]" = {}


def read_static(filename: str) -> str:
    return (
        pathlib.Path(str(resources.files("hyprtxt"))) / "static" / filename
    ).read_text()


STATIC = {
    "default.html": read_static("default.html"),
    "main.css": read_static("main.css"),
    "main.js": read_static("main.js"),
}


class Element:
    def __init__(
        self,
        elem: str,
        /,
        *inner: "str | Element | list[Element | str] | None",
        **properties,
    ) -> None:
        self.children: list[Element | str] = []

        for inner_part in inner:
            self.children.extend(
                []
                if inner_part is None
                else [inner_part]
                if not isinstance(inner_part, list)
                else inner_part
            )

        self.elem_name = elem
        self.properties = properties

    def text(self) -> str:
        void_tag = False

        if not self.children and "@vt" in self.properties:
            del self.properties["@vt"]
            void_tag = True

        generated = f"<{self.elem_name}"

        if self.properties:
            generated += " "
            generated += " ".join(
                [
                    f"{k.removesuffix('_kw')}={repr(v)}"
                    for k, v in self.properties.items()
                ]
            )

        if void_tag:
            generated += "/>"
        else:
            generated += ">"
        for child in self.children:
            if isinstance(child, Element):
                generated += child.text()
            else:
                generated += str(child)

        if not void_tag:
            generated += f"</{self.elem_name}>"

        return generated


class Page:
    def __init__(self, path: str, ws: websockets.ServerConnection) -> None:
        self.path = path
        self._hooks: dict[str, dict[str, Callable[[str, str], Awaitable[None]]]] = {}
        self._ws = ws
        self._pending_requests = {}

    async def setup_page(self):
        pass

    async def hook(
        self, id: str, action: str, func: Callable[[str, str], Awaitable[None]]
    ):
        if id not in self._hooks:
            self._hooks[id] = {}

        self._hooks[id][action] = func
        await self._ws.send(
            json.dumps(
                {
                    "type": "add_filter",
                    "id": id,
                    "action": action.removeprefix("on"),
                }
            )
        )

    async def _rec_action(self, id: str, action: str):
        try:
            func = self._hooks[id][action]
        except KeyError:
            return

        await func(id, action)

    async def add_child(self, content: str | Element, below: str = "body"):
        await self._ws.send(
            json.dumps(
                {
                    "type": "add_child",
                    "content": content.text()
                    if isinstance(content, Element)
                    else str(content),
                    "below": below,
                }
            )
        )

    async def set_text(self, id: str, content: str):
        await self._ws.send(
            json.dumps({"type": "set_text", "id": id, "content": content})
        )

    async def get_text(self, id: str) -> str:
        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        await self._ws.send(
            json.dumps({"type": "get_text", "id": id, "request_id": request_id})
        )

        return await future

    async def get_prop(self, id: str, prop: str):
        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[request_id] = future

        await self._ws.send(
            json.dumps(
                {"type": "get_prop", "id": id, "prop": prop, "request_id": request_id}
            )
        )
        return await future

    async def set_prop(self, id: str, prop: str, value):
        await self._ws.send(
            json.dumps({"type": "set_prop", "id": id, "prop": prop, "value": value})
        )

    async def add_style(self, style: str | io.TextIOBase):
        if isinstance(style, io.TextIOBase):
            style_string = style.read()
        else:
            style_string = str(style)

        await self.add_child(Element("style", style_string), "head")


@dataclass
class Content:
    string: bytes | str | BaseException
    status_code: int = 200
    headers: dict[str, str] = dataclasses.field(default_factory=lambda: dict())


class Provider:
    def __init__(self, get_path: Callable[[str], Content], priority: int = 100) -> None:
        if priority < 0:
            raise ValueError("cannot have priority less than zero")

        self.get_path = get_path
        self.priority = priority
        self.sub_providers: list[Provider] = []


def run_app(providers: list[Provider], *, host: str = "0.0.0.0", port: int = 7777):
    asyncio.run(_run(providers, host, port))


async def _run(providers: list[Provider], host: str, port: int):
    async def _procreq_wrapper(conn, req):
        return await _process_request(providers, conn, req)

    providers_s = sorted(providers, key=lambda x: -x.priority)
    providers = []

    for provider in providers_s:
        providers.append(provider)
        providers.extend(getattr(provider, "sub_providers", []))

    async with serve(
        handler=_handle_ws,
        host=host,
        port=port,
        process_request=_procreq_wrapper,
    ) as server:
        proc = server.serve_forever()

        await proc


async def _handle_ws(websocket: websockets.ServerConnection):
    path = str(await websocket.recv())

    if path in pages or "*" in pages:
        await websocket.send(json.dumps({"pathmsg": "success", "error_pretty": ""}))
    else:
        await websocket.send(
            json.dumps(
                {
                    "pathmsg": "unknown",
                    "error_pretty": f'Path not found on server for "{path}"',
                }
            )
        )
        return

    try:
        page = pages[path](path, websocket)
    except KeyError:
        page = pages["*"](path, websocket)

    asyncio.create_task(page.setup_page())

    try:
        async for raw in websocket:
            payload = json.loads(raw)

            match payload.get("type", "ping"):
                case "ping":
                    continue
                case "triggered":
                    asyncio.create_task(
                        page._rec_action(payload["id"], payload["action"])
                    )
                case "query_response":
                    qid = payload.get("query_id")
                    if qid in page._pending_requests:
                        page._pending_requests[qid].set_result(payload.get("data"))
                        del page._pending_requests[qid]
                case "got_text":
                    req_id = payload.get("request_id")
                    if req_id in page._pending_requests:
                        page._pending_requests[req_id].set_result(
                            payload.get("content")
                        )
                        del page._pending_requests[req_id]
                case "got_prop":
                    req_id = payload.get("request_id")
                    if req_id in page._pending_requests:
                        page._pending_requests[req_id].set_result(
                            payload.get("content")
                        )
                        del page._pending_requests[req_id]
    except ConnectionClosed:
        pass


async def _process_request(
    providers: list[Provider],
    connection: websockets.ServerConnection,
    request: websockets.Request,
) -> websockets.Response | None:
    if request.path.strip("/") == "_hyprtxt/ws":
        return
    for prov in providers:
        content = prov.get_path(request.path)
        if content is None:
            continue

        if isinstance(content.string, BaseException):
            into = io.StringIO()
            traceback.print_exception(content.string, file=into)

            string = into.getvalue().encode()
        elif isinstance(content.string, str):
            string = content.string.encode(errors="replace")
        elif isinstance(content.string, bytes):
            string = content.string
        else:
            string = bytes(content.string)

        return websockets.Response(
            content.status_code, "", websockets.Headers(**content.headers), string
        )

    else:
        error = "no providers for the request, make sure there is at least one with a catch-all"
        return websockets.Response(
            500, error, websockets.Headers(), body=error.encode()
        )
