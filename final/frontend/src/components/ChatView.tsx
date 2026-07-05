import type { ChatMessage } from "../types";
import { Composer } from "./Composer";
import { MessageList } from "./MessageList";

interface ChatViewProps {
  title: string;
  messages: ChatMessage[];
  isGenerating: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

export function ChatView({ title, messages, isGenerating, onSend, onStop }: ChatViewProps) {
  return (
    <main className="chat">
      <header className="topbar">
        <h1 className="topbar__title">{title}</h1>
        <span className="topbar__model">
          <span className="topbar__status" aria-hidden="true"></span>
          llama3.1:8b
        </span>
      </header>

      <MessageList messages={messages} isGenerating={isGenerating} />

      <Composer isGenerating={isGenerating} onSend={onSend} onStop={onStop} />
    </main>
  );
}
