/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base de l'API backend (défaut : http://localhost:8000). */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
