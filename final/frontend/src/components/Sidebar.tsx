import type { Conversation } from "../types";
import { ConversationItem } from "./ConversationItem";

interface SidebarProps {
  conversations: Conversation[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export function Sidebar({
  conversations,
  currentId,
  onSelect,
  onNew,
  onRename,
  onDelete,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar__header">
        <span className="sidebar__logo" aria-hidden="true">◆</span>
        <span className="sidebar__brand">Chatbot Local</span>
      </div>

      <button className="sidebar__new" type="button" onClick={onNew}>
        <svg
          className="sidebar__new-icon"
          viewBox="0 0 16 16"
          width="14"
          height="14"
          aria-hidden="true"
        >
          <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        Nouvelle conversation
      </button>

      <div className="sidebar__label">Conversations</div>

      <ul className="conv-list">
        {conversations.map((conversation) => (
          <ConversationItem
            key={conversation.id}
            conversation={conversation}
            active={conversation.id === currentId}
            onSelect={() => onSelect(conversation.id)}
            onRename={(title) => onRename(conversation.id, title)}
            onDelete={() => {
              if (window.confirm("Supprimer cette conversation ?")) {
                onDelete(conversation.id);
              }
            }}
          />
        ))}
      </ul>
    </aside>
  );
}
