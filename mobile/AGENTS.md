# Agents Realtime Implementation Guide

This document explains how the Expo mobile app (`client/`) and Node server (`backend/`) work together to support OpenAI’s Realtime WebRTC stack, the tooling loop, and multimodal UX. It supplements `tech-arch.md` with repository-specific details.

---

## 1. Architecture Overview
- **Mobile client** (Expo Router) captures microphone audio, negotiates a WebRTC session with the backend, streams assistant deltas, collects transcripts, and lets users submit text or camera images.
- **Backend server** proxies SDP offers to `https://api.openai.com/v1/realtime/calls`, configures the session, and maintains the Sideband WebSocket to execute tools and return results. The client never calls OpenAI directly.
- **Realtime model**: `gpt-realtime` with audio+text modalities, Whisper transcription, server VAD, and configurable voice/instructions.

```
┌────────────┐   offer SDP    ┌─────────────┐   FormData {sdp,session}   ┌────────────────────────┐
│ Expo app   │ ─────────────▶ │ backend     │ ─────────────────────────▶ │ OpenAI /v1/realtime    │
│ (WebRTC)   │                 │ /session    │                            │ calls + sideband WS    │
└────────────┘ ◀───────────── └─────────────┘ ◀───────────────────────── └────────────────────────┘
       ▲                               │                ▲
       │ audio/data channel             │ tools via WS  │
       └────────── transcripts + UI ◀───┴───────────────┘
```

---

## 2. Backend (`backend/server.ts`)
1. **Environment**  
   - `OPENAI_API_KEY` (required)  
   - Optional overrides: `REALTIME_INSTRUCTIONS`, `REALTIME_VOICE`, `PORT`.
2. **Session config**  
   - `modalities: ["audio", "text"]` enables text deltas alongside audio playback.  
   - `input_audio_transcription` defaults to Whisper for user transcripts displayed in the UI.  
   - `audio.input.vad.type = "server_vad"` delegates turn-taking to the platform.  
3. **/session route**  
   - Accepts the SDP offer (raw body with `Content-Type: application/sdp`).  
   - Creates `FormData { sdp, session }` and POSTs to OpenAI.  
   - Returns the upstream SDP answer directly to the client.
4. **Sideband tools**  
   - After receiving the `Location` header, opens `wss://api.openai.com/v1/realtime?call_id=...`.  
   - Registers example tools (`delayed_add`, `echo_upper`) and stores pending invocation args.  
   - Buffers `response.function_call_arguments.delta`, executes helper async functions, and replies with `conversation.item.create` (type `function_call_output`) followed by `response.create`.  
5. **Error handling**  
   - Logs Sideband `error` events, catches tool execution failures, and responds with JSON error payloads to keep the model loop alive.

**Run locally**
```bash
cd backend
OPENAI_API_KEY=sk-... npm run typecheck   # optional
OPENAI_API_KEY=sk-... node --env-file=.env server.ts
```
TypeScript is configured with `noEmit`; use `tsx` or `ts-node` if you prefer to run it directly during iteration.

---

## 3. Mobile Client (`client/`)
### 3.1 Project layout
```
client/
  app/
    _layout.tsx            # Expo Router stack container
    index.tsx              # Entry renders VoiceChatScreen inside SafeAreaView
  src/
    realtime/OpenAIRealtimeClient.ts
    screens/VoiceChatScreen.tsx
    components/CameraModal.tsx
```

### 3.2 Realtime client
`OpenAIRealtimeClient` wraps `react-native-webrtc`:
- captures microphone audio via `mediaDevices.getUserMedia`.
- adds tracks to an `RTCPeerConnection` and creates `oai-events` data channel.
- posts the SDP offer to `${SERVER_BASE_URL}/session`; applies the answer.
- exposes helpers to send text (`input_text`) and images (Base64 JPEG) plus arbitrary events.
- emits callbacks for assistant deltas, completed responses, user transcription, and errors.
- Handles missing TypeScript definitions by treating `RTCDataChannel` as `any` (known issue in `react-native-webrtc` typings).

### 3.3 VoiceChatScreen UX
- **Start/Stop** buttons control the session lifecycle and append system messages.
- **Assistant stream** displays running deltas and completed responses in a chat-style FlatList.
- **Text input** sends typed prompts.  
- **CameraModal** requests permissions, captures Base64 JPEGs, and posts them along with a default instruction (`"Please describe this photo in detail."`).
- Uses `Constants.expoConfig?.extra?.SERVER_BASE_URL` to find the backend (falls back to `http://localhost:3000` for local dev). Set this via `app.config.js` or app.json extras when targeting devices.

### 3.4 Running the client
Requires an Expo Dev Client (React Native WebRTC is not available in Expo Go).
```bash
cd client
npm install   # already done in repo bootstrap
npm run prebuild   # iOS scaffolding, cleans pods each time
expo run:ios --device   # or configure Android once implemented
```
Ensure your device can reach the backend host (use LAN IP or tunneling if needed).

---

## 4. Tooling & Extensibility
- **Adding tools**: register additional `function` definitions in `session.update`, then extend `runTool` with real implementations. The pending map is keyed by `call_id` to handle concurrent requests safely.
- **Streaming UI**: `assistantBufferRef` accumulates `response.text.delta` chunks; on `response.text.done`/`response.done` the buffer is flushed to the transcript list.
- **Custom session behavior**: adjust `sessionConfig` or send additional `session.update` payloads from either the backend or data channel (e.g., change instructions mid-call).
- **Vision prompts**: the default camera instruction is purposefully generic; tweak it or expose UI controls for user-provided captions.
- **Multi-call handling**: the current app maintains a single `OpenAIRealtimeClient` instance. For multi-room scenarios, create separate instances and manage component state accordingly.

---

## 5. Known Issues & Workarounds
- `react-native-webrtc` typings lack `RTCDataChannel` and `RTCSessionDescriptionType`; the client uses `any` and `RTCSessionDescription` constructor to stay type-safe enough while avoiding the upstream issue (see https://github.com/react-native-webrtc/react-native-webrtc/issues/1700). Keep the workaround until typings are updated.
- Expo Dev Client build times increase because `prebuild --clean` runs on each CI/CD invocation. Consider switching to manual `expo prebuild` plus incremental `pod install` once the project stabilizes.
- Sideband WebSocket assumes the call remains active. On connection errors, the backend currently logs and relies on the model to terminate; add reconnection or cleanup logic if needed.

---

## 6. Testing Checklist
1. **Server**  
   - `npm run typecheck` to validate TypeScript.  
   - Start server with `.env` containing `OPENAI_API_KEY`.  
   - Hit `GET /health` to confirm readiness.
2. **Device run**  
   - Launch the Expo Dev Client, tap *Start*.  
   - Speak → user transcript appears, assistant responds via streaming text/audio.  
   - Send typed text → assistant provides follow-up.  
   - Tap *Take photo…* → capture image, verify AI description arrives (text + spoken).  
   - Trigger tools by asking the assistant to “add 2 and 5 slowly” or “uppercase hello”.
3. **Regression guardrails**  
   - Watch Metro logs for `react-native-webrtc` permission errors.  
   - Confirm the data channel stays open (no “send failed” warnings).  
   - Observe server logs for tool execution or Sideband disconnects.

---

## 7. Operational Notes
- Keep backend and client on the same LAN or provide a tunnel/HTTPS endpoint for real devices.
- Rotate API keys regularly and never commit them. Prefer `.env` files plus the iOS secure store for app builds.
- For production, proxy `/session` through your existing auth stack so only authenticated users can start calls.
- Consider persisting transcripts by hooking the `entries` state into a lightweight storage layer once privacy requirements are finalized.

---

Questions or updates? Coordinate with the backend and mobile maintainers before changing session schema, tool naming conventions, or Expo project configuration. Shared understanding keeps the real-time experience reliable. ***
