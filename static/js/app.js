// Ajoute un bouton « afficher/masquer » (œil) à chaque champ mot de passe de
// la page, sans avoir à y penser dans chaque gabarit (CDC 7.3 — ergonomie).
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll('input[type="password"]').forEach(function (champ) {
    if (champ.closest(".password-field")) return; // déjà habillé

    const enveloppe = document.createElement("div");
    enveloppe.className = "password-field";
    champ.parentNode.insertBefore(enveloppe, champ);
    enveloppe.appendChild(champ);

    const bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "password-toggle";
    bouton.innerHTML = '<i class="bi bi-eye" aria-hidden="true"></i>';
    bouton.setAttribute("aria-label", "Afficher le mot de passe");
    bouton.setAttribute("aria-pressed", "false");
    enveloppe.appendChild(bouton);

    bouton.addEventListener("click", function () {
      const visible = champ.type === "text";
      champ.type = visible ? "password" : "text";
      bouton.querySelector("i").className = visible ? "bi bi-eye" : "bi bi-eye-slash";
      bouton.setAttribute("aria-pressed", String(!visible));
      bouton.setAttribute("aria-label", visible ? "Afficher le mot de passe" : "Masquer le mot de passe");
    });
  });
});
