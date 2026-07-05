// =========================================================================
// Chatbot Local — logique de l'interface (étape 15)
//
// Ajouts par rapport à l'étape 14 (tout est CÔTÉ CLIENT, le backend ne change
// pas) :
//   1. rendu Markdown des réponses du modèle (gras, listes, code…) ;
//   2. bouton « Arrêter » pour interrompre une génération en cours ;
//   4. bouton « Copier » et horodatage sur chaque message (session courante).
// =========================================================================

// ----- Références aux éléments de la page -----
const messagesEl = document.getElementById("messages"); // zone qui défile
const messagesInnerEl = document.getElementById("messages-inner"); // colonne centrée
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const convListEl = document.getElementById("conv-list");
const newConvBtn = document.getElementById("new-conv");

// Icônes du bouton d'envoi (flèche = envoyer, carré = arrêter).
const ICON_SEND =
  '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">' +
  '<path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_STOP =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
  '<rect x="3" y="3" width="10" height="10" rx="2" fill="currentColor"/></svg>';
sendBtn.innerHTML = ICON_SEND;

// État partagé.
let currentConversationId = null;
let isGenerating = false; // une réponse est-elle en cours de streaming ?
let abortController = null; // permet d'interrompre le fetch /chat en cours

// ----- Couche d'accès à l'API (pendant client du CRUD serveur) -----
const api = {
  list: () => fetch("/conversations").then((r) => r.json()),
  create: () => fetch("/conversations", { method: "POST" }).then((r) => r.json()),
  messages: (id) => fetch(`/conversations/${id}`).then((r) => r.json()),
  remove: (id) => fetch(`/conversations/${id}`, { method: "DELETE" }),
  rename: (id, title) =>
    fetch(`/conversations/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    }),
};

// =========================================================================
// (1) Rendu Markdown — minimal, SANS dépendance, et SÛR.
//
// Principe de sécurité : on échappe TOUT le HTML d'abord. La sortie du modèle
// n'est jamais du HTML de confiance ; en échappant en premier, le pire cas est
// un formatage imparfait, jamais une injection de <script>.
// =========================================================================

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Transformations « inline » (à l'intérieur d'un paragraphe / titre / item).
function renderInline(text) {
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>"); // **gras**
  text = text.replace(/__([^_]+)__/g, "<strong>$1</strong>"); //     __gras__
  text = text.replace(/\*([^*\n]+)\*/g, "<em>$1</em>"); //           *italique*
  text = text.replace(/(^|[^\w])_([^_\n]+)_(?=[^\w]|$)/g, "$1<em>$2</em>"); // _italique_
  text = text.replace( //                                    [texte](https://…)
    /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  return text;
}

function renderMarkdown(src) {
  let text = escapeHtml(src);

  // Sortir les blocs de code ``` ``` (leur contenu ne doit pas être transformé).
  const codeBlocks = [];
  text = text.replace(/```[^\n]*\n?([\s\S]*?)```/g, (_, code) => {
    codeBlocks.push(code.replace(/\n$/, ""));
    return ` CODEBLOCK${codeBlocks.length - 1} `;
  });

  // Sortir le code inline `…` de la même façon.
  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    inlineCodes.push(code);
    return ` INLINECODE${inlineCodes.length - 1} `;
  });

  // Assemblage bloc par bloc (ligne à ligne) : titres, listes, paragraphes.
  const lines = text.split("\n");
  const out = [];
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) {
      out.push(`<p>${renderInline(paragraph.join("<br>"))}</p>`);
      paragraph = [];
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const block = line.match(/^ CODEBLOCK(\d+) $/);
    if (block) {
      flush();
      out.push(`<pre class="md-code"><code>${codeBlocks[+block[1]]}</code></pre>`);
      i++;
    } else if (/^### /.test(line)) {
      flush();
      out.push(`<h3>${renderInline(line.slice(4))}</h3>`);
      i++;
    } else if (/^## /.test(line)) {
      flush();
      out.push(`<h2>${renderInline(line.slice(3))}</h2>`);
      i++;
    } else if (/^# /.test(line)) {
      flush();
      out.push(`<h1>${renderInline(line.slice(2))}</h1>`);
      i++;
    } else if (/^\s*[-*] /.test(line)) {
      flush();
      const items = [];
      while (i < lines.length && /^\s*[-*] /.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].replace(/^\s*[-*] /, ""))}</li>`);
        i++;
      }
      out.push(`<ul>${items.join("")}</ul>`);
    } else if (/^\s*\d+\. /.test(line)) {
      flush();
      const items = [];
      while (i < lines.length && /^\s*\d+\. /.test(lines[i])) {
        items.push(`<li>${renderInline(lines[i].replace(/^\s*\d+\. /, ""))}</li>`);
        i++;
      }
      out.push(`<ol>${items.join("")}</ol>`);
    } else if (line.trim() === "") {
      flush();
      i++;
    } else {
      paragraph.push(line);
      i++;
    }
  }
  flush();

  let html = out.join("");
  // Restaurer le code inline, puis tout bloc de code resté dans un paragraphe.
  html = html.replace(/ INLINECODE(\d+) /g, (_, n) => `<code>${inlineCodes[+n]}</code>`);
  html = html.replace(
    / CODEBLOCK(\d+) /g,
    (_, n) => `<pre class="md-code"><code>${codeBlocks[+n]}</code></pre>`
  );
  return html;
}

// =========================================================================
// (4) Fabrique de message : bulle + méta (horodatage + bouton Copier).
// =========================================================================

/** Heure locale « HH:MM » pour l'horodatage d'un message de la session. */
function nowTime() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Affiche l'état vide (conversation sans message). */
function showEmptyState() {
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.innerHTML =
    '<div class="empty__icon" aria-hidden="true">◆</div>' +
    '<h2 class="empty__title">Comment puis-je vous aider ?</h2>' +
    '<p class="empty__hint">Posez une question pour démarrer la conversation.</p>';
  messagesInnerEl.appendChild(empty);
}

/**
 * Ajoute un message au fil et renvoie un « handle » pour l'alimenter.
 * @param {"user"|"bot"} role
 * @param {{markdown?: boolean, time?: string|null, text?: string}} opts
 */
function addMessage(role, { markdown = false, time = null, text = "" } = {}) {
  // Le premier message remplace l'état vide, le cas échéant.
  messagesInnerEl.querySelector(".empty")?.remove();

  const msg = document.createElement("div");
  msg.className = `msg msg--${role}`;

  // Avatar (bot uniquement : l'utilisateur est identifié par l'alignement).
  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "msg__avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "◆";
    msg.appendChild(avatar);
  }

  const body = document.createElement("div");
  body.className = "msg__body";
  msg.appendChild(body);

  const bubble = document.createElement("div");
  bubble.className = `bubble bubble--${role}`;
  body.appendChild(bubble);

  const meta = document.createElement("div");
  meta.className = "msg__meta";
  if (time) {
    const t = document.createElement("span");
    t.className = "msg__time";
    t.textContent = time;
    meta.appendChild(t);
  }
  const copyBtn = document.createElement("button");
  copyBtn.className = "msg__copy";
  copyBtn.type = "button";
  copyBtn.textContent = "Copier";
  meta.appendChild(copyBtn);
  body.appendChild(meta);

  let raw = text;
  const render = () => {
    if (markdown) bubble.innerHTML = renderMarkdown(raw);
    else bubble.textContent = raw; // les messages utilisateur restent verbatim
  };
  render();

  // Copier COPIE LE TEXTE BRUT (le Markdown source), pas le HTML rendu.
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(raw);
      copyBtn.textContent = "Copié ✓";
    } catch {
      copyBtn.textContent = "Échec";
    }
    setTimeout(() => (copyBtn.textContent = "Copier"), 1200);
  });

  messagesInnerEl.appendChild(msg);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  return {
    get raw() {
      return raw;
    },
    setText(value) {
      raw = value;
      render();
    },
    append(chunk) {
      raw += chunk;
      render();
      messagesEl.scrollTop = messagesEl.scrollHeight;
    },
    setStreaming(on) {
      bubble.classList.toggle("bubble--streaming", on);
    },
  };
}

// ----- VUE LISTE : (re)dessiner la barre latérale -----
async function refreshSidebar() {
  const conversations = await api.list();
  convListEl.replaceChildren();

  // L'en-tête reflète le titre de la conversation active.
  const active = conversations.find((c) => c.id === currentConversationId);
  document.querySelector(".topbar__title").textContent =
    active ? active.title : "Conversation";

  for (const conv of conversations) {
    const item = document.createElement("li");
    item.className = "conv";
    if (conv.id === currentConversationId) item.classList.add("conv--active");
    item.dataset.id = conv.id;

    const title = document.createElement("span");
    title.className = "conv__title";
    title.textContent = conv.title;

    const rename = document.createElement("button");
    rename.className = "conv__rename";
    rename.type = "button";
    rename.textContent = "✎";
    rename.title = "Renommer";

    const del = document.createElement("button");
    del.className = "conv__delete";
    del.type = "button";
    del.textContent = "×";
    del.title = "Supprimer";

    item.append(title, rename, del);
    convListEl.appendChild(item);

    title.addEventListener("click", () => openConversation(conv.id));
    title.addEventListener("dblclick", () => startRename(item, conv));
    rename.addEventListener("click", (event) => {
      event.stopPropagation();
      startRename(item, conv);
    });
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(conv.id);
    });
  }
}

// ----- VUE DÉTAIL : charger et afficher une conversation -----
async function openConversation(id) {
  currentConversationId = id;
  const messages = await api.messages(id);

  messagesInnerEl.replaceChildren();
  if (messages.length === 0) showEmptyState();
  for (const m of messages) {
    // Pas d'horodatage sur l'historique : on ne stocke pas l'heure par message
    // (le modèle de sauvegarde réécrit tous les messages à chaque tour).
    if (m.role === "user") addMessage("user", { text: m.content });
    else addMessage("bot", { markdown: true, text: m.content });
  }
  refreshSidebar();
  inputEl.focus();
}

async function newConversation() {
  const { id } = await api.create();
  await openConversation(id);
}

async function deleteConversation(id) {
  if (!confirm("Supprimer cette conversation ?")) return;
  await api.remove(id);

  if (id === currentConversationId) {
    const remaining = await api.list();
    if (remaining.length > 0) await openConversation(remaining[0].id);
    else await newConversation();
  } else {
    refreshSidebar();
  }
}

/**
 * Édition du titre EN PLACE : le titre devient un champ de saisie.
 * Entrée ou perte de focus = enregistrer (PATCH → persisté en base) ;
 * Échap = annuler. La barre latérale est redessinée dans tous les cas.
 */
function startRename(item, conv) {
  const titleEl = item.querySelector(".conv__title");
  if (!titleEl) return; // déjà en cours d'édition

  const input = document.createElement("input");
  input.className = "conv__edit";
  input.type = "text";
  input.value = conv.title;
  input.maxLength = 80;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  let settled = false; // évite le double déclenchement (Entrée PUIS blur)
  const finish = async (save) => {
    if (settled) return;
    settled = true;
    const trimmed = input.value.trim();
    if (save && trimmed && trimmed !== conv.title) {
      await api.rename(conv.id, trimmed);
    }
    refreshSidebar();
  };

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") finish(true);
    else if (event.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
  // Cliquer dans le champ ne doit pas ouvrir/changer la conversation.
  input.addEventListener("click", (event) => event.stopPropagation());
}

// =========================================================================
// (2) Envoi + streaming, avec bouton « Arrêter ».
// =========================================================================

/** Bascule l'UI entre mode saisie et mode génération (bouton = Arrêter). */
function setGenerating(on) {
  isGenerating = on;
  sendBtn.innerHTML = on ? ICON_STOP : ICON_SEND;
  sendBtn.setAttribute("aria-label", on ? "Arrêter" : "Envoyer");
  sendBtn.classList.toggle("composer__send--stop", on);
  inputEl.disabled = on; // on bloque la saisie pendant la génération…
  sendBtn.disabled = false; // …mais le bouton reste actif pour pouvoir arrêter
}

async function sendMessage(message) {
  addMessage("user", { text: message, time: nowTime() });

  const bot = addMessage("bot", { markdown: true, time: nowTime() });
  bot.setStreaming(true);

  // AbortController : appeler .abort() interrompt le fetch et fait lever une
  // AbortError dans la boucle de lecture ci-dessous.
  abortController = new AbortController();
  setGenerating(true);

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: currentConversationId }),
      signal: abortController.signal,
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      bot.append(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (error.name === "AbortError") {
      // Interruption volontaire : on marque la réponse partielle.
      bot.append("\n\n_(interrompu)_");
    } else {
      bot.setText("[Erreur] Impossible de joindre le serveur.");
    }
  } finally {
    bot.setStreaming(false);
    abortController = null;
    setGenerating(false);
  }

  // NB : un tour interrompu n'est PAS persisté côté serveur (le générateur est
  // abandonné avant la sauvegarde) — il disparaîtra donc au rechargement.
  refreshSidebar();
}

async function handleSend() {
  // En pleine génération, le bouton sert à ARRÊTER.
  if (isGenerating) {
    if (abortController) abortController.abort();
    return;
  }

  const message = inputEl.value.trim();
  if (!message || !currentConversationId) return;

  inputEl.value = "";
  autoResizeInput();
  await sendMessage(message);
  inputEl.focus();
}

/** La zone de saisie grandit avec le texte (plafonnée par max-height en CSS). */
function autoResizeInput() {
  inputEl.style.height = "auto";
  inputEl.style.height = `${inputEl.scrollHeight}px`;
}

// ----- Démarrage -----
async function init() {
  const conversations = await api.list();
  if (conversations.length > 0) await openConversation(conversations[0].id);
  else await newConversation();
}

// ----- Branchement des événements -----
sendBtn.addEventListener("click", handleSend);
newConvBtn.addEventListener("click", newConversation);

inputEl.addEventListener("input", autoResizeInput);

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleSend();
  }
});

init();
