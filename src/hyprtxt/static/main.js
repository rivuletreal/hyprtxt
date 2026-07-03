const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";

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
  const text =
    typeof event.data === "string" ? event.data : await event.data.text();
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
