import { StatusBar } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import VoiceChatScreen from "../src/screens/VoiceChatScreen";

export default function Index() {
  return (
    <SafeAreaView
      style={{ flex: 1, backgroundColor: "#111" }}
      edges={["top", "bottom"]}
    >
      <StatusBar barStyle="light-content" />
      <VoiceChatScreen />
    </SafeAreaView>
  );
}
