/** Une entrée de la barre latérale, telle que renvoyée par GET /conversations. */
export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

/** Un message du fil. `time` et `error` n'existent que côté client :
 *  le backend ne persiste ni l'horodatage ni les erreurs de génération. */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  /** Heure locale « HH:MM » — session courante uniquement. */
  time?: string;
  /** true si le contenu est un message d'erreur (event: error du flux SSE). */
  error?: boolean;
}

/** Un évènement du flux SSE de POST /chat, une fois décodé. */
export type ChatEvent =
  | { type: "token"; text: string }
  | { type: "error"; message: string }
  | { type: "done" };
