import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ChatMessage } from "../types";

interface MessageProps {
  message: ChatMessage;
  /** true pendant que cette bulle reçoit encore des tokens (curseur ▋). */
  streaming: boolean;
}

/**
 * Une bulle + sa méta (horodatage, bouton Copier).
 *
 * Les messages utilisateur restent verbatim ; ceux du bot passent par
 * react-markdown (+ GFM), qui remplace le rendu Markdown artisanal de
 * l'étape 15 — sûr par construction : jamais de HTML injecté.
 */
export function Message({ message, streaming }: MessageProps) {
  const isUser = message.role === "user";
  const [copyLabel, setCopyLabel] = useState("Copier");

  // Copier COPIE LE TEXTE BRUT (le Markdown source), pas le HTML rendu.
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopyLabel("Copié ✓");
    } catch {
      setCopyLabel("Échec");
    }
    setTimeout(() => setCopyLabel("Copier"), 1200);
  };

  const bubbleClass = [
    "bubble",
    isUser ? "bubble--user" : "bubble--bot",
    streaming ? "bubble--streaming" : "",
    message.error ? "bubble--error" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={`msg msg--${isUser ? "user" : "bot"}`}>
      {!isUser && (
        <div className="msg__avatar" aria-hidden="true">◆</div>
      )}
      <div className="msg__body">
        <div className={bubbleClass}>
          {isUser ? (
            message.content
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                // Les liens de la réponse s'ouvrent dans un nouvel onglet.
                a: (props) => (
                  <a {...props} target="_blank" rel="noopener noreferrer" />
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>
        <div className="msg__meta">
          {message.time && <span className="msg__time">{message.time}</span>}
          <button className="msg__copy" type="button" onClick={() => void copy()}>
            {copyLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
