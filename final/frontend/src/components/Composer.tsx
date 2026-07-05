import { useEffect, useRef, useState } from "react";

interface ComposerProps {
  isGenerating: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}

const ICON_SEND = (
  <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
    <path
      d="M8 13V3M3.5 7.5 8 3l4.5 4.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const ICON_STOP = (
  <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
    <rect x="3" y="3" width="10" height="10" rx="2" fill="currentColor" />
  </svg>
);

export function Composer({ isGenerating, onSend, onStop }: ComposerProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // La zone de saisie grandit avec le texte (plafonnée par max-height en CSS).
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, [value]);

  // Fin de génération : la saisie se réactive → on lui rend le focus.
  useEffect(() => {
    if (!isGenerating) textareaRef.current?.focus();
  }, [isGenerating]);

  const handleSend = () => {
    // En pleine génération, le bouton sert à ARRÊTER.
    if (isGenerating) {
      onStop();
      return;
    }
    const text = value.trim();
    if (!text) return;
    setValue("");
    onSend(text);
  };

  return (
    <footer className="composer">
      <div className="composer__box">
        <textarea
          ref={textareaRef}
          className="composer__input"
          rows={1}
          placeholder="Écrivez un message…"
          value={value}
          disabled={isGenerating}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSend();
            }
          }}
        />
        <button
          className={`composer__send${isGenerating ? " composer__send--stop" : ""}`}
          type="button"
          aria-label={isGenerating ? "Arrêter" : "Envoyer"}
          onClick={handleSend}
        >
          {isGenerating ? ICON_STOP : ICON_SEND}
        </button>
      </div>
      <p className="composer__hint">
        <kbd>Entrée</kbd> pour envoyer · <kbd>Maj + Entrée</kbd> pour une nouvelle ligne
      </p>
    </footer>
  );
}
