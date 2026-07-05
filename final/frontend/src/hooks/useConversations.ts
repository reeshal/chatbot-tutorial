// =========================================================================
// useConversations — l'état de la COLLECTION (barre latérale).
//
// Équivalent React de refreshSidebar()/newConversation()/deleteConversation()
// de l'étape 15 : la liste vit dans un state, chaque mutation passe par l'API
// puis re-synchronise la liste depuis le serveur (source de vérité unique).
// =========================================================================

import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client";
import type { Conversation } from "../types";

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);

  /** Recharge la liste depuis le serveur (et la renvoie pour enchaîner). */
  const refresh = useCallback(async (): Promise<Conversation[]> => {
    const list = await api.listConversations();
    setConversations(list);
    return list;
  }, []);

  const createNew = useCallback(async () => {
    const { id } = await api.createConversation();
    await refresh();
    setCurrentId(id);
  }, [refresh]);

  // Démarrage : ouvrir la conversation la plus récente, ou en créer une.
  useEffect(() => {
    void (async () => {
      const list = await refresh();
      if (list.length > 0) setCurrentId(list[0].id);
      else await createNew();
    })();
  }, [refresh, createNew]);

  const rename = useCallback(
    async (id: string, title: string) => {
      await api.renameConversation(id, title);
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      await api.deleteConversation(id);
      const remaining = await refresh();
      // Si on vient de supprimer la conversation OUVERTE, on bascule sur la
      // plus récente restante — ou on en recrée une si tout est vide.
      if (id === currentId) {
        if (remaining.length > 0) setCurrentId(remaining[0].id);
        else await createNew();
      }
    },
    [refresh, createNew, currentId],
  );

  return { conversations, currentId, setCurrentId, refresh, createNew, rename, remove };
}
