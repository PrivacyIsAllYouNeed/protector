import http from "node:http";
import { text } from "node:stream/consumers";
import WebSocket from "ws";

const PORT = Number(process.env.PORT ?? 3000);
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
  throw new Error("Set OPENAI_API_KEY in env");
}

const sessionConfig = {
  type: "realtime",
  model: "gpt-realtime",
  audio: { output: { voice: "marin" } },
};

const server = http.createServer(async (req, res) => {
  try {
    const pathname = req.url ?? "/";

    if (req.method === "POST" && pathname === "/session") {
      const sdp = await text(req);

      const fd = new FormData();
      fd.set("sdp", sdp);
      fd.set("session", JSON.stringify(sessionConfig));

      const upstream = await fetch("https://api.openai.com/v1/realtime/calls", {
        method: "POST",
        headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
        body: fd,
        signal: AbortSignal.timeout(10_000),
      });

      const location = upstream.headers.get("location");
      const callId = location?.split("/").pop();
      if (callId) {
        const url = `wss://api.openai.com/v1/realtime?call_id=${callId}`;
        const ws = new WebSocket(url, {
          headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
        });

        ws.on("open", () => {
          console.log("sideband connected", callId);
          // ws.send(
          //   JSON.stringify({
          //     type: "session.update",
          //     session: { type: "realtime", instructions: "Be extra nice today!" },
          //   })
          // );
        });

        ws.on("message", (d) => {
          try {
            console.log("sideband", JSON.parse(d.toString()));
          } catch {
            console.log("sideband", d.toString());
          }
        });
        ws.on("error", (e) => console.error("sideband error", e));
        ws.on("close", (code, reason) =>
          console.log("sideband closed", callId, code, reason.toString()),
        );
      }

      const t = await upstream.text();
      res.statusCode = upstream.status;
      res.setHeader(
        "Content-Type",
        upstream.headers.get("content-type") ?? "text/plain",
      );
      res.end(t);
      return;
    }

    if (req.method === "GET" && pathname === "/health") {
      res.writeHead(200, { "Content-Type": "text/plain" });
      res.end("ok");
      return;
    }

    res.statusCode = 404;
    res.end("not found");
  } catch (err) {
    console.error(err);
    res.statusCode = 500;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "internal_error" }));
  }
});

server.listen(PORT);
