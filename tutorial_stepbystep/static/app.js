// =========================================================================
// Chatbot Local — logique de l'interface
// Lit la réponse du backend en streaming et l'affiche au fur et à mesure.
// =========================================================================

// ----- Références aux éléments de la page -----
const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");

/**
 * Crée une bulle de message et l'ajoute au fil.
 * Retourne l'élément pour pouvoir y écrire au fur et à mesure (streaming).
 *
 * @param {"user"|"bot"} role - Qui parle ; détermine le style de la bulle.
 * @param {string} text - Contenu initial (vide pour le bot, rempli ensuite).
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

/**
 * Envoie le message au backend et AFFICHE la réponse en streaming.
 *
 * Miroir, côté navigateur, de la boucle Python `for token in session.ask(...)`.
 * On lit le flux fragment par fragment au lieu d'attendre la réponse entière.
 *
 * @param {string} message - Le texte saisi par l'utilisateur.
 */
async function sendMessage(message) {
  addBubble("user", message);

  // Bulle vide du bot : on la remplira token par token.
  const botBubble = addBubble("bot", "");
  botBubble.classList.add("bubble--streaming"); // active le curseur clignotant

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    // response.body est un flux d'OCTETS. On le lit avec un « reader ».
    const reader = response.body.getReader();

    // Le réseau transporte des octets, pas du texte. TextDecoder les
    // reconvertit en chaîne. { stream: true } est crucial : un caractère
    // accentué (é, à) peut être coupé entre deux fragments réseau ; cette
    // option met les octets incomplets en tampon jusqu'au fragment suivant.
    const decoder = new TextDecoder();

    // Boucle équivalente au `for token in ...` de Python.
    while (true) {
      const { value, done } = await reader.read();
      if (done) break; // flux épuisé : le modèle a fini.

      const chunk = decoder.decode(value, { stream: true });
      botBubble.textContent += chunk;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (error) {
    botBubble.textContent = "[Erreur] Impossible de joindre le serveur.";
  } finally {
    // Quoi qu'il arrive, on retire le curseur de streaming.
    botBubble.classList.remove("bubble--streaming");
  }
}

/**
 * Gère un envoi : vide le champ, désactive les contrôles pendant la
 * génération (la session est partagée côté serveur, on évite deux
 * requêtes simultanées), puis les réactive.
 */
async function handleSend() {
  const message = inputEl.value.trim();
  if (!message) return;

  inputEl.value = "";
  sendBtn.disabled = true;
  inputEl.disabled = true;

  await sendMessage(message);

  sendBtn.disabled = false;
  inputEl.disabled = false;
  inputEl.focus();
}

// ----- Branchement des événements -----

// Clic sur « Envoyer ».
sendBtn.addEventListener("click", handleSend);

// Entrée = envoyer ; Maj+Entrée = nouvelle ligne.
inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    handleSend();
  }
});