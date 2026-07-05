import { useRef, useState } from "react";

import type { Conversation } from "../types";

interface ConversationItemProps {
  conversation: Conversation;
  active: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onDelete: () => void;
}

/**
 * Une entrée de la liste. Le renommage « en place » de l'étape 15
 * (titleEl.replaceWith(input)) devient un simple état `editing` : on rend
 * soit le titre, soit un champ de saisie.
 */
export function ConversationItem({
  conversation,
  active,
  onSelect,
  onRename,
  onDelete,
}: ConversationItemProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(conversation.title);
  // Évite le double déclenchement Entrée PUIS blur (les deux appellent finish).
  const settledRef = useRef(false);

  const startEditing = () => {
    setDraft(conversation.title);
    settledRef.current = false;
    setEditing(true);
  };

  const finish = (save: boolean) => {
    if (settledRef.current) return;
    settledRef.current = true;
    setEditing(false);
    const trimmed = draft.trim();
    if (save && trimmed && trimmed !== conversation.title) {
      onRename(trimmed);
    }
  };

  return (
    <li className={`conv${active ? " conv--active" : ""}`}>
      {editing ? (
        <input
          className="conv__edit"
          type="text"
          value={draft}
          maxLength={80}
          autoFocus
          onFocus={(event) => event.target.select()}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") finish(true);
            else if (event.key === "Escape") finish(false);
          }}
          onBlur={() => finish(true)}
          onClick={(event) => event.stopPropagation()}
        />
      ) : (
        <span
          className="conv__title"
          onClick={onSelect}
          onDoubleClick={startEditing}
        >
          {conversation.title}
        </span>
      )}

      <button
        className="conv__rename"
        type="button"
        title="Renommer"
        onClick={(event) => {
          event.stopPropagation();
          startEditing();
        }}
      >
        ✎
      </button>
      <button
        className="conv__delete"
        type="button"
        title="Supprimer"
        onClick={(event) => {
          event.stopPropagation();
          onDelete();
        }}
      >
        ×
      </button>
    </li>
  );
}
