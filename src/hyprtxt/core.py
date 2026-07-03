import asyncio
import io
import json
import uuid
from collections.abc import Awaitable, Callable
from importlib import resources

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

pages: "dict[str, type[Page]]" = {}


def read_static(filename: str) -> str:
    return resources.files("hyprtxt.static").joinpath(filename).read_text()


STATIC = {
    "default.html": read_static("default.html"),
    "main.css": read_static("main.css"),
    "main.js": read_static("main.js"),
}


@app.middleware("http")
async def clear_and_set_csp(request, call_next):
    response = await call_next(request)
    if "content-security-policy" in response.headers:
        del response.headers["content-security-policy"]

    response.headers["Content-Security-Policy"] = (
        "default-src 'self' 'unsafe-inline'; connect-src 'self' wss: ws:"
    )
    return response


@app.websocket("/_hyprtxt/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()

    path = await websocket.receive_text()

    if path in pages or "*" in pages:
        await websocket.send_text(
            json.dumps({"pathmsg": "success", "error_pretty": ""})
        )
    else:
        await websocket.send_text(
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

    while True:
        try:
            payload = json.loads(await websocket.receive_text())
        except WebSocketDisconnect:
            break

        match payload.get("type", "ping"):
            case "ping":
                continue
            case "triggered":
                asyncio.create_task(page._rec_action(payload["id"], payload["action"]))
            case "query_response":
                qid = payload.get("query_id")
                if qid in page._pending_requests:
                    page._pending_requests[qid].set_result(payload.get("data"))
                    del page._pending_requests[qid]
            case "got_text":
                req_id = payload.get("request_id")
                if req_id in page._pending_requests:
                    page._pending_requests[req_id].set_result(payload.get("content"))
                    del page._pending_requests[req_id]
            case "got_prop":
                req_id = payload.get("request_id")
                if req_id in page._pending_requests:
                    page._pending_requests[req_id].set_result(payload.get("content"))
                    del page._pending_requests[req_id]


@app.get("/_hyprtxt/main.js")
async def _():
    return Response(STATIC["main.js"], media_type="text/javascript")


@app.get("/_hyprtxt/main.css")
async def _():
    return Response(STATIC["main.css"], media_type="text/css")


@app.get("/{full_path:path}")
async def all_pages_html(full_path):
    return HTMLResponse(
        STATIC["default.html"].replace("${noscript-err}", full_path),
    )


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
    def __init__(self, path: str, ws: WebSocket) -> None:
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
        await self._ws.send_text(
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
        await self._ws.send_text(
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
        await self._ws.send_text(
            json.dumps({"type": "set_text", "id": id, "content": content})
        )

    async def get_text(self, id: str) -> str:
        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        await self._ws.send_text(
            json.dumps({"type": "get_text", "id": id, "request_id": request_id})
        )

        return await future

    async def get_prop(self, id: str, prop: str):
        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[request_id] = future

        await self._ws.send_text(
            json.dumps(
                {"type": "get_prop", "id": id, "prop": prop, "request_id": request_id}
            )
        )
        return await future

    async def set_prop(self, id: str, prop: str, value):
        await self._ws.send_text(
            json.dumps({"type": "set_prop", "id": id, "prop": prop, "value": value})
        )

    async def add_style(self, style: str | io.TextIOBase):
        if isinstance(style, io.TextIOBase):
            style_string = style.read()
        else:
            style_string = str(style)

        await self.add_child(Element("style", style_string), "head")
