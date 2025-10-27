import { SafeAreaView, StatusBar } from "react-native";
import VoiceChatScreen from "../src/screens/VoiceChatScreen";

export default function Index() {
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: "#111" }}>
      <StatusBar barStyle="light-content" />
      <VoiceChatScreen />
    </SafeAreaView>
  );
}
