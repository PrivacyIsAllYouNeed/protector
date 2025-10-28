import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  TextInput,
  FlatList,
} from "react-native";
import Constants from "expo-constants";
import OpenAIRealtimeClient, {
  TranscriptEntry,
} from "../realtime/OpenAIRealtimeClient";
import CameraModal from "../components/CameraModal";

function createEntry(
  role: TranscriptEntry["role"],
  text: string,
): TranscriptEntry {
  return {
    id: Math.random().toString(36).slice(2),
    role,
    text,
  };
}

export default function VoiceChatScreen() {
  const serverBaseUrl =
    (Constants?.expoConfig?.extra as Record<string, unknown>)
      ?.SERVER_BASE_URL ?? "http://localhost:3000";

  const client = useMemo(
    () =>
      new OpenAIRealtimeClient({
        serverBaseUrl: String(serverBaseUrl),
      }),
    [serverBaseUrl],
  );

  const [running, setRunning] = useState(false);
  const [cameraVisible, setCameraVisible] = useState(false);
  const [entries, setEntries] = useState<TranscriptEntry[]>([]);
  const [assistantBuffer, setAssistantBuffer] = useState("");
  const [text, setText] = useState("");

  const assistantBufferRef = useRef("");

  const append = useCallback((entry: TranscriptEntry) => {
    setEntries((prev) => [...prev, entry]);
  }, []);

  useEffect(() => {
    client.onTranscriptDelta = (_, delta) => {
      assistantBufferRef.current = `${assistantBufferRef.current}${delta}`;
      setAssistantBuffer(assistantBufferRef.current);
    };
    client.onTranscriptDone = () => {
      if (assistantBufferRef.current.trim().length) {
        append(createEntry("assistant", assistantBufferRef.current));
        assistantBufferRef.current = "";
        setAssistantBuffer("");
      }
    };
    client.onUserTranscript = (transcript) => {
      append(createEntry("user", transcript));
    };
    client.onError = (error) => {
      append(createEntry("system", `Error: ${error.message}`));
    };

    return () => {
      client.onTranscriptDelta = null;
      client.onTranscriptDone = null;
      client.onUserTranscript = null;
      client.onServerEvent = null;
      client.onError = null;
      assistantBufferRef.current = "";
      setAssistantBuffer("");
    };
  }, [client, append]);

  useEffect(() => {
    return () => {
      client.stop().catch(() => undefined);
    };
  }, [client]);

  return (
    <View style={{ flex: 1, backgroundColor: "#111", paddingTop: 12 }}>
      <View style={{ paddingHorizontal: 16, gap: 12 }}>
        {!running ? (
          <TouchableOpacity
            style={{
              backgroundColor: "#2e7d32",
              padding: 14,
              borderRadius: 10,
              alignItems: "center",
            }}
            onPress={async () => {
              try {
                await client.start();
                setRunning(true);
                append(createEntry("system", "Session started."));
              } catch (error) {
                const message =
                  error instanceof Error ? error.message : String(error);
                append(createEntry("system", `Failed to start: ${message}`));
                setRunning(false);
              }
            }}
          >
            <Text style={{ color: "#fff", fontSize: 16, fontWeight: "600" }}>
              Start
            </Text>
          </TouchableOpacity>
        ) : (
          <>
            <TouchableOpacity
              style={{
                backgroundColor: "#c62828",
                padding: 14,
                borderRadius: 10,
                alignItems: "center",
              }}
              onPress={async () => {
                await client.stop();
                setRunning(false);
                append(createEntry("system", "Session stopped."));
              }}
            >
              <Text style={{ color: "#fff", fontSize: 16, fontWeight: "600" }}>
                Stop
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={{
                backgroundColor: "#1565c0",
                padding: 14,
                borderRadius: 10,
                alignItems: "center",
              }}
              onPress={() => setCameraVisible(true)}
            >
              <Text
                style={{ color: "#fff", fontSize: 16, textAlign: "center" }}
              >
                Take photo and ask AI to describe
              </Text>
            </TouchableOpacity>

            <View style={{ flexDirection: "row", gap: 8 }}>
              <TextInput
                value={text}
                onChangeText={setText}
                placeholder="Type text to send"
                placeholderTextColor="#999"
                style={{
                  flex: 1,
                  backgroundColor: "#222",
                  color: "#fff",
                  paddingHorizontal: 12,
                  paddingVertical: 12,
                  borderRadius: 8,
                }}
              />
              <TouchableOpacity
                style={{
                  backgroundColor: "#424242",
                  paddingHorizontal: 18,
                  borderRadius: 8,
                  justifyContent: "center",
                }}
                onPress={() => {
                  const trimmed = text.trim();
                  if (!trimmed) return;
                  append(createEntry("user", trimmed));
                  client.sendUserText(trimmed);
                  setText("");
                }}
              >
                <Text style={{ color: "#fff", fontWeight: "600" }}>Send</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>

      <View style={{ flex: 1, marginTop: 16 }}>
        <FlatList
          data={entries}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 24 }}
          ItemSeparatorComponent={() => <View style={{ height: 12 }} />}
          renderItem={({ item }) => (
            <View
              style={{
                alignSelf:
                  item.role === "assistant"
                    ? "flex-start"
                    : item.role === "user"
                      ? "flex-end"
                      : "center",
                maxWidth: "85%",
                backgroundColor:
                  item.role === "assistant"
                    ? "#1e88e5"
                    : item.role === "user"
                      ? "#424242"
                      : "#333",
                padding: 12,
                borderRadius: 12,
              }}
            >
              <Text style={{ color: "white" }}>
                {item.role.toUpperCase()}: {item.text}
              </Text>
            </View>
          )}
          ListFooterComponent={
            assistantBuffer ? (
              <View
                style={{
                  alignSelf: "flex-start",
                  backgroundColor: "#1e88e5",
                  padding: 12,
                  borderRadius: 12,
                  marginTop: 12,
                  maxWidth: "85%",
                }}
              >
                <Text style={{ color: "white" }}>
                  ASSISTANT: {assistantBuffer}
                </Text>
              </View>
            ) : null
          }
          ListEmptyComponent={() => (
            <View
              style={{
                flex: 1,
                alignItems: "center",
                justifyContent: "center",
                paddingTop: 48,
              }}
            >
              <Text style={{ color: "#777" }}>
                No transcript yet. Tap Start to begin.
              </Text>
            </View>
          )}
        />
      </View>

      <CameraModal
        visible={cameraVisible}
        onClose={() => setCameraVisible(false)}
        onShot={(base64) => {
          append(createEntry("user", "Sent a photo."));
          client.sendUserImageBase64JPEG(
            base64,
            "Please describe this photo in detail.",
          );
        }}
      />
    </View>
  );
}
