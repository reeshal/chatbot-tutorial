// =========================================================================
// useChatStream — l'état d'UNE conversation (le fil de messages) et le
// streaming de la réponse.
//
// L'étape 15 alimentait le DOM impérativement (bot.append(chunk)) ; ici le
// flux est inversé : les fragments s'accumulent dans un state React et le
// composant se re-rend à chaque chunk. Le bouton « Arrêter » repose sur le
// même AbortController que la version vanilla.
// =========================================================================

import { useCallback, useEffect, useRef, useState } from "react";

import { api, streamChat } from "../api/client";
import type { ChatMessage } from "../types";

/** Heure locale « HH:MM » pour l'horodatage d'un message de la session. */
function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function useChatStream(
  conversationId: string | null,
  onTurnComplete: () => void,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Changement de conversation : on interrompt le flux en cours, puis on
  // charge l'historique de la nouvelle (sans horodatage : il n'est pas stocké).
  useEffect(() => {
    abortRef.current?.abort();
    setMessages([]);
    if (conversationId === null) return;

    let cancelled = false; // ignore la réponse si on a re-changé entre-temps
    void api.getMessages(conversationId).then((history) => {
      if (!cancelled) setMessages(history);
    });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  /** Remplace le DERNIER message du fil (la bulle du bot en cours). */
  const updateLast = (updater: (message: ChatMessage) => ChatMessage) => {
    setMessages((previous) =>
      previous.map((message, index) =>
        index === previous.length - 1 ? updater(message) : message,
      ),
    );
  };

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    async (text: string) => {
      if (conversationId === null || isGenerating) return;

      // La question + une bulle bot vide qui se remplira au fil des tokens.
      setMessages((previous) => [
        ...previous,
        { role: "user", content: text, time: nowTime() },
        { role: "assistant", content: "", time: nowTime() },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      setIsGenerating(true);

      try {
        for await (const event of streamChat(conversationId, text, controller.signal)) {
          if (event.type === "token") {
            updateLast((m) => ({ ...m, content: m.content + event.text }));
          } else if (event.type === "error") {
            // Erreur TYPÉE (Ollama absent…) : le serveur a annulé le tour.
            updateLast((m) => ({ ...m, content: event.message, error: true }));
          } else {
            // done : le tour est persisté et la conversation titrée →
            // la barre latérale doit refléter le nouveau titre/ordre.
            onTurnComplete();
          }
        }
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          // Interruption volontaire : on marque la réponse partielle.
          // NB : un tour interrompu n'est PAS persisté côté serveur (le
          // générateur est abandonné avant la sauvegarde).
          updateLast((m) => ({ ...m, content: `${m.content}\n\n*(interrompu)*` }));
        } else {
          updateLast((m) => ({
            ...m,
            content: "Impossible de joindre le serveur.",
            error: true,
          }));
        }
      } finally {
        abortRef.current = null;
        setIsGenerating(false);
      }
    },
    [conversationId, isGenerating, onTurnComplete],
  );

  return { messages, isGenerating, send, stop };
}
