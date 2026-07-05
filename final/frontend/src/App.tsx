import { ChatView } from "./components/ChatView";
import { Sidebar } from "./components/Sidebar";
import { useChatStream } from "./hooks/useChatStream";
import { useConversations } from "./hooks/useConversations";

export default function App() {
  const { conversations, currentId, setCurrentId, refresh, createNew, rename, remove } =
    useConversations();

  // `refresh` en fin de tour : le backend vient de titrer la conversation
  // (autotitle) et de mettre à jour updated_at → la barre latérale suit.
  const { messages, isGenerating, send, stop } = useChatStream(currentId, refresh);

  const activeTitle =
    conversations.find((c) => c.id === currentId)?.title ?? "Conversation";

  return (
    <div className="layout">
      <Sidebar
        conversations={conversations}
        currentId={currentId}
        onSelect={setCurrentId}
        onNew={() => void createNew()}
        onRename={(id, title) => void rename(id, title)}
        onDelete={(id) => void remove(id)}
      />
      <ChatView
        title={activeTitle}
        messages={messages}
        isGenerating={isGenerating}
        onSend={(text) => void send(text)}
        onStop={stop}
      />
    </div>
  );
}
