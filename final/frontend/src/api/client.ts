// =========================================================================
// Couche d'accès à l'API — pendant client du contrat exposé par le backend.
//
// Le frontend et l'API vivent sur des origins DIFFÉRENTS (5173 / 8000) :
// toutes les URLs sont donc absolues, construites sur API_BASE. Le backend
// autorise cet origin via CORS.
// =========================================================================

import type { ChatEvent, ChatMessage, Conversation } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** fetch + contrôle du statut + décodage JSON, mutualisés. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} sur ${path}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listConversations: () => request<Conversation[]>("/conversations"),

  createConversation: () =>
    request<{ id: string }>("/conversations", { method: "POST" }),

  getMessages: (id: string) => request<ChatMessage[]>(`/conversations/${id}`),

  renameConversation: (id: string, title: string) =>
    request<{ id: string; title: string }>(`/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),

  deleteConversation: (id: string) =>
    request<{ ok: boolean }>(`/conversations/${id}`, { method: "DELETE" }),
};

// =========================================================================
// Streaming de /chat.
//
// Le serveur répond au format SSE (event/data/ligne vide), mais on ne peut
// pas utiliser EventSource : il ne sait pas envoyer un POST avec corps JSON.
// On lit donc le corps du fetch en flux (ReadableStream) et on décode les
// évènements nous-mêmes. L'AbortSignal permet le bouton « Arrêter ».
// =========================================================================

/** Décode UN bloc SSE brut (les lignes entre deux lignes vides). */
function parseEvent(raw: string): ChatEvent | null {
  let eventType = "message";
  const dataLines: string[] = [];

  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) eventType = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;

  const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
  switch (eventType) {
    case "token":
      return { type: "token", text: String(data.text ?? "") };
    case "error":
      return { type: "error", message: String(data.message ?? "Erreur inconnue") };
    case "done":
      return { type: "done" };
    default:
      return null; // type inconnu : on l'ignore, le protocole peut évoluer
  }
}

/** Envoie un message et produit les évènements du flux, un par un. */
export async function* streamChat(
  conversationId: string,
  message: string,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversation_id: conversationId }),
    signal,
  });
  if (!response.ok || response.body === null) {
    throw new Error(`HTTP ${response.status} sur /chat`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Un évènement SSE se termine par une ligne vide ("\n\n"). Le réseau
    // peut couper n'importe où : on ne consomme que les blocs COMPLETS,
    // le reste attend le prochain paquet dans le tampon.
    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const event = parseEvent(raw);
      if (event) yield event;
    }
  }
}
