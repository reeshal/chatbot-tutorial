// =========================================================================
// Chatbot Local — logique de l'interface (étape 13 : liste de conversations)
//
// Deux vues qui se répondent :
//   - LISTE   : la barre latérale, alimentée par GET /conversations ;
//   - DÉTAIL  : le fil de la conversation active, GET /conversations/{id}.
// =========================================================================

// ----- Références aux éléments de la page -----
const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const convListEl = document.getElementById("conv-list");
const newConvBtn = document.getElementById("new-conv");

// L'unique état partagé : quelle conversation est ouverte.
let currentConversationId = null;

// ----- Petite couche d'accès à l'API (le pendant client du CRUD serveur) -----
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

/**
 * Crée une bulle de message et l'ajoute au fil.
 * @param {"user"|"bot"} role - Qui parle ; détermine le style de la bulle.
 * @param {string} text - Contenu initial.
 * @returns {HTMLDivElement} La bulle créée.
 */
function addBubble(role, text) {
  const bubble = document.createElement("div");
  bubble.className = `bubble bubble--${role}`;
  bubble.textContent = text;
  messagesEl.appendChild(bubble);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

// ----- VUE LISTE : (re)dessiner la barre latérale -----

/**
 * Récupère les conversations et reconstruit la liste, en surlignant l'active.
 */
async function refreshSidebar() {
  const conversations = await api.list();
  convListEl.replaceChildren(); // vide la liste avant de la reconstruire

  for (const conv of conversations) {
    const item = document.createElement("li");
    item.className = "conv";
    if (conv.id === currentConversationId) item.classList.add("conv--active");
    item.dataset.id = conv.id;

    const title = document.createElement("span");
    title.className = "conv__title";
    title.textContent = conv.title;

    const del = document.createElement("button");
    del.className = "conv__delete";
    del.type = "button";
    del.textContent = "×";
    del.title = "Supprimer";

    item.append(title, del);
    convListEl.appendChild(item);

    // Clic sur l'entrée → ouvrir le DÉTAIL de cette conversation.
    title.addEventListener("click", () => openConversation(conv.id));
    // Double-clic sur le titre → renommer (la partie « U » du CRUD).
    title.addEventListener("dblclick", () => renameConversation(conv.id, conv.title));
    // Clic sur × → supprimer (stopPropagation : ne pas ouvrir en même temps).
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(conv.id);
    });
  }
}

// ----- VUE DÉTAIL : charger et afficher une conversation -----

/**
 * Ouvre une conversation : charge ses messages et remplit le fil.
 * @param {string} id - Identifiant de la conversation à ouvrir.
 */
async function openConversation(id) {
  currentConversationId = id;
  const messages = await api.messages(id);

  messagesEl.replaceChildren(); // on repart d'un fil vide
  for (const message of messages) {
    // Le store parle en rôles « user »/« assistant » ; l'UI en « user »/« bot ».
    addBubble(message.role === "user" ? "user" : "bot", message.content);
  }
  refreshSidebar(); // met à jour le surlignage de l'entrée active
  inputEl.focus();
}

/**
 * Crée une conversation vierge et l'ouvre aussitôt.
 */
async function newConversation() {
  const { id } = await api.create();
  await openConversation(id); // openConversation rafraîchit déjà la liste
}

/**
 * Supprime une conversation. Si c'était l'active, bascule sur une autre
 * (ou en recrée une) pour ne jamais laisser l'UI sans conversation ouverte.
 */
async function deleteConversation(id) {
  if (!confirm("Supprimer cette conversation ?")) return;
  await api.remove(id);

  if (id === currentConversationId) {
    const remaining = await api.list();
    if (remaining.length > 0) {
      await openConversation(remaining[0].id);
    } else {
      await newConversation();
    }
  } else {
    refreshSidebar();
  }
}

/**
 * Renomme une conversation via une simple invite.
 */
async function renameConversation(id, current) {
  const title = prompt("Nouveau titre :", current);
  if (title === null) return; // annulé
  const trimmed = title.trim();
  if (!trimmed) return;
  await api.rename(id, trimmed);
  refreshSidebar();
}

// ----- Envoi d'un message (streaming, comme avant) -----

/**
 * Envoie le message au backend et AFFICHE la réponse en streaming.
 * @param {string} message - Le texte saisi par l'utilisateur.
 */
async function sendMessage(message) {
  addBubble("user", message);

  const botBubble = addBubble("bot", "");
  botBubble.classList.add("bubble--streaming");

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, conversation_id: currentConversationId }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      botBubble.textContent += chunk;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (error) {
    botBubble.textContent = "[Erreur] Impossible de joindre le serveur.";
  } finally {
    botBubble.classList.remove("bubble--streaming");
  }

  // Le titre (déduit du 1er message) et l'ordre (updated_at) ont pu changer :
  // on resynchronise la barre latérale.
  refreshSidebar();
}

/**
 * Gère un envoi : vide le champ, désactive les contrôles pendant la
 * génération, puis les réactive.
 */
async function handleSend() {
  const message = inputEl.value.trim();
  if (!message || !currentConversationId) return;

  inputEl.value = "";
  sendBtn.disabled = true;
  inputEl.disabled = true;

  await sendMessage(message);

  sendBtn.disabled = false;
  inputEl.disabled = false;
  inputEl.focus();
}

// ----- Démarrage : ouvrir la conversation la plus récente (ou en créer une) -----
async function init() {
  const conversations = await api.list();
  if (conversations.length > 0) {
    await openConversation(conversations[0].id);
  } else {
    await newConversation();
  }
}

// ----- Branchement des événements -----
sendBtn.addEventListener("click", handleSend);
newConvBtn.addEventListener("click", newConversation);

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleSend();
  }
});

init();
