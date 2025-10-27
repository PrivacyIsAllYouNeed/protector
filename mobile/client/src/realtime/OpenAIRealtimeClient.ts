import {
  RTCPeerConnection,
  RTCSessionDescription,
  mediaDevices,
  MediaStream,
} from "react-native-webrtc";

type Listener = (evt: unknown) => void;

async function waitForIceGatheringComplete(pc: RTCPeerConnection) {
  if (pc.iceGatheringState === "complete") {
    return;
  }

  await new Promise<void>((resolve) => {
    let finished = false;

    const peer = pc as any;
    const previousStateHandler = peer.onicegatheringstatechange;
    const previousCandidateHandler = peer.onicecandidate;

    const finish = () => {
      if (finished) return;
      finished = true;
      peer.onicegatheringstatechange = previousStateHandler ?? null;
      peer.onicecandidate = previousCandidateHandler ?? null;
      resolve();
    };

    const timeoutId = setTimeout(() => finish(), 5_000);

    const complete = () => {
      clearTimeout(timeoutId);
      finish();
    };

    peer.onicegatheringstatechange = (event: any) => {
      previousStateHandler?.(event);
      if (pc.iceGatheringState === "complete") {
        complete();
      }
    };

    peer.onicecandidate = (event: any) => {
      previousCandidateHandler?.(event);
      if (!event.candidate) {
        complete();
      }
    };
  });
}

export type TranscriptRole = "user" | "assistant" | "system";

export type TranscriptEntry = {
  id: string;
  role: TranscriptRole;
  text: string;
};

export type OpenAIRealtimeClientOptions = {
  serverBaseUrl: string;
  instructions?: string;
};

export default class OpenAIRealtimeClient {
  private pc: RTCPeerConnection | null = null;
  // react-native-webrtc types do not surface RTCDataChannel yet.
  private dc: any | null = null;
  private localStream: MediaStream | null = null;
  private started = false;

  // event listeners
  onServerEvent: Listener | null = null;
  onTranscriptDelta: ((role: TranscriptRole, delta: string) => void) | null =
    null;
  onTranscriptDone: ((role: TranscriptRole, text: string) => void) | null =
    null;
  onUserTranscript: ((text: string) => void) | null = null;
  onError: ((err: Error) => void) | null = null;

  constructor(private readonly options: OpenAIRealtimeClientOptions) {}

  async start() {
    if (this.started) {
      return;
    }
    this.started = true;

    try {
      // Capture mic audio
      const stream = await mediaDevices.getUserMedia({
        audio: true,
        video: false,
      });
      this.localStream = stream;

      // Create peer connection
      this.pc = new RTCPeerConnection({
        iceServers: [{ urls: ["stun:stun.l.google.com:19302"] }],
      });

      // Attach existing tracks
      stream.getTracks().forEach((track) => {
        this.pc?.addTrack(track, stream);
      });

      // Data channel for realtime events
      this.dc = this.pc.createDataChannel("oai-events");
      this.dc.onmessage = (event: { data: string }) =>
        this.handleServerMessage(event.data);

      // Remote audio plays automatically; no UI element required
      // @ts-ignore react-native-webrtc exposes ontrack at runtime
      this.pc.ontrack = () => undefined;

      // Generate offer and send to backend
      const offer = await this.pc.createOffer({
        offerToReceiveAudio: true,
        offerToReceiveVideo: false,
      });
      await this.pc.setLocalDescription(offer);

      await waitForIceGatheringComplete(this.pc);

      const localSdp = this.pc.localDescription?.sdp;
      if (!localSdp) {
        throw new Error("Missing localDescription after ICE gathering");
      }

      const response = await fetch(
        `${this.options.serverBaseUrl.replace(/\/$/, "")}/session`,
        {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: localSdp,
        },
      );

      if (!response.ok) {
        throw new Error(
          `/session failed: ${response.status} ${await response.text()}`,
        );
      }

      const answerSdp = await response.text();
      await this.pc.setRemoteDescription(
        new RTCSessionDescription({
          type: "answer",
          sdp: answerSdp,
        }),
      );
    } catch (error) {
      this.started = false;
      this.teardown();
      throw error;
    }
  }

  async stop() {
    if (!this.started) {
      return;
    }
    this.started = false;
    this.teardown();
  }

  sendUserText(text: string) {
    if (!this.dc || this.dc.readyState !== "open") return;

    const createEvent = {
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: [{ type: "input_text", text }],
      },
    };
    const respondEvent = { type: "response.create" };

    this.dc.send(JSON.stringify(createEvent));
    this.dc.send(JSON.stringify(respondEvent));
  }

  sendUserImageBase64JPEG(base64: string, instruction?: string) {
    if (!this.dc || this.dc.readyState !== "open") return;

    const parts: Array<Record<string, unknown>> = [];
    if (instruction?.trim()) {
      parts.push({ type: "input_text", text: instruction });
    }
    parts.push({
      type: "input_image",
      image_url: `data:image/jpeg;base64,${base64}`,
    });

    const createEvent = {
      type: "conversation.item.create",
      item: {
        type: "message",
        role: "user",
        content: parts,
      },
    };
    const respondEvent = { type: "response.create" };

    this.dc.send(JSON.stringify(createEvent));
    this.dc.send(JSON.stringify(respondEvent));
  }

  sendEvent(payload: unknown) {
    if (!this.dc || this.dc.readyState !== "open") return;
    this.dc.send(JSON.stringify(payload));
  }

  private handleServerMessage(raw: string) {
    let message: any;
    try {
      message = JSON.parse(raw);
    } catch {
      return;
    }

    this.onServerEvent?.(message);

    switch (message.type) {
      case "response.text.delta":
        this.onTranscriptDelta?.("assistant", message.delta ?? "");
        break;
      case "response.text.done":
        if (typeof message?.text === "string") {
          this.onTranscriptDone?.("assistant", message.text);
        }
        break;
      case "response.done":
        if (typeof message?.response?.output_text === "string") {
          this.onTranscriptDone?.("assistant", message.response.output_text);
        } else {
          this.onTranscriptDone?.("assistant", "");
        }
        break;
      case "conversation.item.input_audio_transcription.completed":
        if (message.transcript) {
          this.onUserTranscript?.(message.transcript);
        }
        break;
      case "error":
        this.onError?.(
          new Error(message?.error?.message ?? "Realtime session error"),
        );
        break;
      default:
        break;
    }
  }

  private teardown() {
    try {
      this.dc?.close();
      this.pc?.getTransceivers().forEach((transceiver) => {
        try {
          transceiver.stop?.();
        } catch {
          /* ignore */
        }
      });
      this.pc?.close();
    } finally {
      this.dc = null;
      this.pc = null;
      this.localStream?.getTracks().forEach((track) => track.stop());
      this.localStream = null;
    }
  }
}
