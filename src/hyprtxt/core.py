import asyncio
import io
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

try:
    import orjson as json
except ImportError:
    import json

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

pages: "dict[str, type[Page]]" = {}

STATIC = {
    "default.html": """<!doctype html>
    <html>
        <head id="head">
            <script async src="/_hyprtxt/main.js"></script>
            <link rel="preload" href="/_hyprtxt/main.css" as="style" />
        </head>
        <body id="body">
            <noscript>
                <link rel="stylesheet" href="/_hyprtxt/main.css" />
                <h1 id="error">
                    Scripts must be enabled to run page for "/${noscript-err}"
                </h1>
            </noscript>
        </body>
    </html>
""",
    "main.css": """body {
        background-color: #222;
        color: #fff;
        font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    }

    #error {
        text-align: center;
        text-decoration: underline mediumvioletred;
    }

    #chat-container {
        display: flex;
        flex-direction: column;
        max-width: 800px;
        margin: 0 auto;
        height: 100vh;
        padding: 1rem;
        box-sizing: border-box;
    }

    #chat-messages {
        flex: 1;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        padding: 1rem 0;
    }

    .chat-message {
        padding: 0.75rem 1rem;
        border-radius: 12px;
        max-width: 75%;
        line-height: 1.5;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.95rem;
        word-wrap: break-word;
    }

    .user-message {
        background-color: mediumvioletred;
        color: #fff;
        align-self: flex-end;
        border-bottom-right-radius: 3px;
    }

    .ai-message {
        background-color: #333;
        color: #e0e0e0;
        align-self: flex-start;
        border-bottom-left-radius: 3px;
    }

    #chat-input-area {
        display: flex;
        gap: 0.5rem;
        padding-top: 0.75rem;
        border-top: 1px solid #444;
    }

    #chat-input {
        flex: 1;
        background-color: #333;
        color: #fff;
        border: 1px solid #555;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.95rem;
        outline: none;
        resize: none;
    }

    #chat-input:focus {
        border-color: mediumvioletred;
    }

    #chat-input::placeholder {
        color: #888;
    }
    body {
        background-color: #222;
        color: #fff;
        font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
    }

    #error {
        text-align: center;
        text-decoration: underline mediumvioletred;
    }

    #app {
        display: flex;
        height: 100vh;
        overflow: hidden;
    }

    #chat-container {
        display: flex;
        flex-direction: column;
        flex: 1;
        padding: 1rem;
        box-sizing: border-box;
        min-width: 0;
        transition: flex 0.3s ease;
    }

    #chat-messages {
        flex: 1;
        overflow-y: auto;
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        padding: 1rem 0;
    }

    .chat-message {
        padding: 0.75rem 1rem;
        border-radius: 12px;
        max-width: 75%;
        line-height: 1.5;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.95rem;
        word-wrap: break-word;
    }

    .user-message {
        background-color: mediumvioletred;
        color: #fff;
        align-self: flex-end;
        border-bottom-right-radius: 3px;
    }

    .ai-message {
        background-color: #333;
        color: #e0e0e0;
        align-self: flex-start;
        border-bottom-left-radius: 3px;
    }

    #chat-input-area {
        display: flex;
        gap: 0.5rem;
        padding-top: 0.75rem;
        border-top: 1px solid #444;
    }

    #chat-input {
        flex: 1;
        background-color: #333;
        color: #fff;
        border: 1px solid #555;
        border-radius: 8px;
        padding: 0.75rem 1rem;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.95rem;
        outline: none;
        resize: none;
    }

    #chat-input:focus {
        border-color: mediumvioletred;
    }

    #chat-input::placeholder {
        color: #888;
    }

    /* ── settings sidebar ── */

    #settings-sidebar {
        width: 33%;
        min-width: 280px;
        background-color: #1a1a1a;
        border-left: 1px solid #444;
        display: flex;
        flex-direction: column;
        transition:
            width 0.3s ease,
            min-width 0.3s ease,
            padding 0.3s ease;
        overflow: hidden;
    }

    #settings-sidebar.collapsed {
        width: 0;
        min-width: 0;
    }

    #settings-toggle {
        position: fixed;
        right: 1rem;
        top: 1rem;
        background: #333;
        border: 1px solid #555;
        color: #fff;
        border-radius: 8px;
        padding: 0.4rem 0.75rem;
        cursor: pointer;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.85rem;
        z-index: 10;
        transition: background 0.2s;
    }

    #settings-toggle:hover {
        background: mediumvioletred;
        border-color: mediumvioletred;
    }

    #settings-content {
        padding: 1rem;
        overflow-y: auto;
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
    }

    #settings-sidebar.collapsed #settings-content {
        display: none;
    }

    .settings-group {
        display: flex;
        flex-direction: column;
        gap: 0.4rem;
    }

    .settings-group label {
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.8rem;
        color: #aaa;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    .settings-group input[type="text"],
    .settings-group input[type="number"],
    .settings-group select,
    .settings-group textarea {
        background: #2a2a2a;
        border: 1px solid #555;
        border-radius: 6px;
        color: #fff;
        padding: 0.5rem 0.75rem;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.9rem;
        outline: none;
        width: 100%;
        box-sizing: border-box;
    }

    .settings-group input:focus,
    .settings-group select:focus,
    .settings-group textarea:focus {
        border-color: mediumvioletred;
    }

    .settings-group input[type="range"] {
        -webkit-appearance: none;
        width: 100%;
        height: 4px;
        border-radius: 2px;
        background: #444;
        outline: none;
    }

    .settings-group input[type="range"]::-webkit-slider-thumb {
        -webkit-appearance: none;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: mediumvioletred;
        cursor: pointer;
    }

    .settings-group .range-row {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }

    .settings-group .range-value {
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.85rem;
        color: #ccc;
        min-width: 2.5rem;
        text-align: right;
    }

    .settings-group .multi-choice {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
    }

    .settings-group .choice-btn {
        background: #2a2a2a;
        border: 1px solid #555;
        border-radius: 6px;
        color: #ccc;
        padding: 0.35rem 0.75rem;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 0.85rem;
        cursor: pointer;
        transition: all 0.15s;
    }

    .settings-group .choice-btn.active,
    .settings-group .choice-btn:hover {
        background: mediumvioletred;
        border-color: mediumvioletred;
        color: #fff;
    }

    #settings-header {
        padding: 1rem;
        border-bottom: 1px solid #444;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 1rem;
        font-weight: 600;
        color: #fff;
        flex-shrink: 0;
    }
""",
    "main.js": """const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";

    const socket = new WebSocket(`${wsProtocol}//${window.location.host}/_hyprtxt/ws`);
    let isPathMsg = true;

    const activeFilters = new Set();

    socket.onopen = (event) => {
      socket.send(window.location.pathname);

      setInterval(() => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send("{}");
        }
      }, 30000);
    };

    socket.onmessage = async (event) => {
      const text = await event.data.text;
      let msg = JSON.parse(text);

      if (isPathMsg) {
        isPathMsg = false;
        if (msg.pathmsg != "success") {
          let err = msg.error_pretty;
          document.body.insertAdjacentHTML("beforeend", `<h1 id="error">${err}</h1>`);
          document.head.insertAdjacentHTML(
            "beforeend",
            `<link rel="stylesheet" href="/_hyprtxt/main.css" />`,
          );
          socket.close();
        }
        return;
      }
      switch (msg.type) {
        case "add_child": {
          document
            .getElementById(msg.below)
            .insertAdjacentHTML("beforeend", msg.content);
          break;
        }
        case "add_filter": {
          activeFilters.add(`${msg.id}:${msg.action}`);
          break;
        }
        case "set_text":
          document.getElementById(msg.id).innerText = msg.content;
          break;

        case "get_text":
          const val = document.getElementById(msg.id).innerText;
          socket.send(
            JSON.stringify({
              type: "query_response",
              query_id: msg.query_id,
              data: val,
            }),
          );
          break;
        case "get_prop": {
          const el = document.getElementById(msg.id);
          let val = null;

          if (el) {
            const path = msg.prop.split(".");
            val = el;
            for (const part of path) {
              if (val) val = val[part];
            }
          }

          socket.send(
            JSON.stringify({
              type: "got_prop",
              request_id: msg.request_id,
              content: val,
            }),
          );
          break;
        }
        case "set_prop": {
          const el = document.getElementById(msg.id);
          if (el) {
            const path = msg.prop.split(".");
            let obj = el;
            for (let i = 0; i < path.length - 1; i++) {
              obj = obj[path[i]];
              if (!obj) break;
            }
            if (obj) obj[path[path.length - 1]] = msg.value;
          }
          break;
        }
        case "get_prop": {
          const el = document.getElementById(msg.id);
          const val = el
            ? msg.prop.split(".").reduce((o, i) => (o ? o[i] : null), el)
            : null;

          socket.send(
            JSON.stringify({
              type: "got_prop",
              request_id: msg.request_id,
              content: val,
            }),
          );
          break;
        }
      }
    };

    const allPossibleEvents = Object.keys(window)
      .filter((key) => key.startsWith("on"))
      .map((key) => key.slice(2));

    allPossibleEvents.forEach((eventType) => {
      document.addEventListener(
        eventType,
        (e) => {
          const filterKey = `${e.target.id}:${eventType}`;

          if (e.target && e.target.id && activeFilters.has(filterKey)) {
            const payload = {
              type: "triggered",
              action: eventType,
              id: e.target.id,
            };

            socket.send(JSON.stringify(payload));
          }
        },
        { capture: true, passive: true },
      );
    });
""",
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
