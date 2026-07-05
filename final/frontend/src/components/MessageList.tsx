import { useEffect, useRef } from "react";

import type { ChatMessage } from "../types";
import { EmptyState } from "./EmptyState";
import { Message } from "./Message";

interface MessageListProps {
  messages: ChatMessage[];
  isGenerating: boolean;
}

export function MessageList({ messages, isGenerating }: MessageListProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  // Suivre le fil : on colle le défilement en bas à chaque nouveau contenu
  // (l'équivalent du messagesEl.scrollTop = scrollHeight de l'étape 15).
  useEffect(() => {
    const scroller = scrollerRef.current;
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
  }, [messages]);

  return (
    <div className="messages" ref={scrollerRef}>
      <div className="messages__inner">
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          messages.map((message, index) => (
            <Message
              key={index}
              message={message}
              // Seule la DERNIÈRE bulle (celle du bot en cours) clignote.
              streaming={isGenerating && index === messages.length - 1}
            />
          ))
        )}
      </div>
    </div>
  );
}
