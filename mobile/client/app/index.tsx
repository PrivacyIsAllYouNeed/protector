import React, { useRef, useState } from "react";
import { View, Text, Button, ScrollView } from "react-native";
import {
  RTCPeerConnection,
  RTCSessionDescription,
  RTCIceCandidate,
} from "react-native-webrtc";

const SERVER_URL = "ws://192.168.40.69:3001"; // FIXME

export default function Index() {
  const [status, setStatus] = useState("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const log = (s: string) => setLogs((p) => [...p, s]);

  const start = async () => {
    setStatus("connecting");

    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });
    pcRef.current = pc;

    const dc = pc.createDataChannel("probe");
    dcRef.current = dc as any;

    // @ts-ignore
    dc.addEventListener("open", () => {
      log("datachannel open");
      dc.send("ping");
    });

    // @ts-ignore
    dc.addEventListener("message", (ev: any) => {
      log("recv: " + ev.data);
    });

    // @ts-ignore
    pc.addEventListener("icecandidate", (e: any) => {
      if (e.candidate && wsRef.current?.readyState === 1) {
        wsRef.current.send(
          JSON.stringify({ type: "candidate", candidate: e.candidate }),
        );
      }
    });

    // @ts-ignore
    pc.addEventListener("connectionstatechange", () => {
      log("pc state: " + pc.connectionState);
    });

    const ws = new WebSocket(SERVER_URL);
    wsRef.current = ws;

    ws.onopen = async () => {
      log("ws open");
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      ws.send(JSON.stringify(offer)); // { type:'offer', sdp:'...' }
      setStatus("waiting-answer");
      log("offer sent");
    };

    ws.onmessage = async (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "answer") {
        await pc.setRemoteDescription(new RTCSessionDescription(msg));
        log("answer set");
      } else if (msg.type === "candidate" && msg.candidate) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(msg.candidate));
        } catch (e) {
          log("addIceCandidate error: " + e);
        }
      }
    };

    ws.onerror = () => log("ws error");
    ws.onclose = () => log("ws close");
  };

  const stop = () => {
    dcRef.current && (dcRef.current as any).close?.();
    pcRef.current && pcRef.current.close();
    wsRef.current && wsRef.current.close();
    dcRef.current = null;
    pcRef.current = null;
    wsRef.current = null;
    setStatus("idle");
    log("stopped");
  };

  return (
    <View style={{ flex: 1, padding: 16, gap: 8 }}>
      <Text style={{ fontWeight: "bold", fontSize: 18 }}>WebRTC Probe</Text>
      <Text>Status: {status}</Text>
      <View style={{ flexDirection: "row", gap: 12 }}>
        <Button title="Start" onPress={start} />
        <Button title="Stop" onPress={stop} />
      </View>
      <ScrollView style={{ flex: 1, backgroundColor: "#eee", padding: 8 }}>
        {logs.map((l, i) => (
          <Text key={i} style={{ fontFamily: "monospace" }}>
            {l}
          </Text>
        ))}
      </ScrollView>
    </View>
  );
}
