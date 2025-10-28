import http from "node:http";
import { text } from "node:stream/consumers";
import WebSocket from "ws";

const PORT = Number(process.env.PORT ?? 3000);
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
  throw new Error("Set OPENAI_API_KEY in env");
}

const SESSION_INSTRUCTIONS = "You are a helpful voice assistant.";
const SESSION_VOICE = "marin";

const sessionConfig = {
  type: "realtime",
  model: "gpt-realtime",
  modalities: ["audio", "text"],
  input_audio_transcription: { model: "whisper-1" },
  audio: {
    input: { vad: { type: "server_vad" } },
    output: { voice: SESSION_VOICE },
  },
  instructions: SESSION_INSTRUCTIONS,
};

type PendingTool = { name: string; args: string };

async function delayedAdd({ a, b }: { a: number; b: number }) {
  await new Promise((resolve) => setTimeout(resolve, 800));
  return { sum: Number(a) + Number(b) };
}

async function echoUpper({ text: value }: { text: string }) {
  await new Promise((resolve) => setTimeout(resolve, 400));
  return { result: String(value).toUpperCase() };
}

async function runTool(
  name: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  switch (name) {
    case "delayed_add":
      return delayedAdd(args as { a: number; b: number });
    case "echo_upper":
      return echoUpper(args as { text: string });
    default:
      return { error: `unknown tool: ${name}` };
  }
}

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
        const pendingByCallId = new Map<string, PendingTool>();
        const url = `wss://api.openai.com/v1/realtime?call_id=${callId}`;
        const ws = new WebSocket(url, {
          headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
        });

        ws.on("open", () => {
          console.log("sideband connected", callId);
          ws.send(
            JSON.stringify({
              type: "session.update",
              session: {
                instructions: SESSION_INSTRUCTIONS,
                tools: [
                  {
                    type: "function",
                    name: "delayed_add",
                    description: "Add two numbers slowly",
                    parameters: {
                      type: "object",
                      properties: {
                        a: { type: "number" },
                        b: { type: "number" },
                      },
                      required: ["a", "b"],
                    },
                  },
                  {
                    type: "function",
                    name: "echo_upper",
                    description: "Uppercase a string",
                    parameters: {
                      type: "object",
                      properties: { text: { type: "string" } },
                      required: ["text"],
                    },
                  },
                ],
              },
            }),
          );
        });

        ws.on("message", async (raw) => {
          let msg: any;
          try {
            msg = JSON.parse(raw.toString());
          } catch {
            console.log("sideband", raw.toString());
            return;
          }

          if (
            msg.type === "response.output_item.added" &&
            msg.item?.type === "function_call"
          ) {
            const { call_id: pendingId, name } = msg.item;
            if (pendingId && name) {
              pendingByCallId.set(pendingId, { name, args: "" });
            }
            return;
          }

          if (msg.type === "response.function_call_arguments.delta") {
            const pending = pendingByCallId.get(msg.call_id);
            if (pending) pending.args += msg.delta ?? "";
            return;
          }

          if (msg.type === "response.function_call_arguments.done") {
            const call = msg.call_id;
            const pending = pendingByCallId.get(call);
            if (!pending) return;
            pendingByCallId.delete(call);

            let parsed: Record<string, unknown>;
            try {
              parsed = JSON.parse(pending.args || msg.arguments || "{}");
            } catch {
              parsed = { _raw: pending.args ?? msg.arguments };
            }

            try {
              const output = await runTool(pending.name, parsed);
              ws.send(
                JSON.stringify({
                  type: "conversation.item.create",
                  item: {
                    type: "function_call_output",
                    call_id: call,
                    output: JSON.stringify(output),
                  },
                }),
              );
            } catch (error) {
              ws.send(
                JSON.stringify({
                  type: "conversation.item.create",
                  item: {
                    type: "function_call_output",
                    call_id: call,
                    output: JSON.stringify({
                      error: error instanceof Error ? error.message : String(error),
                    }),
                  },
                }),
              );
            }

            ws.send(JSON.stringify({ type: "response.create" }));
            return;
          }

          if (msg.type === "error") {
            console.error("sideband error", msg);
            return;
          }
        });

        ws.on("close", (code, reason) => {
          pendingByCallId.clear();
          console.log("sideband closed", callId, code, reason.toString());
        });
        ws.on("error", (error) => console.error("sideband error", error));
      }

      const body = await upstream.text();
      res.statusCode = upstream.status;
      res.setHeader(
        "Content-Type",
        upstream.headers.get("content-type") ?? "text/plain",
      );
      res.end(body);
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

server.listen(PORT, () => {
  console.log(`server on :${PORT}`);
});
