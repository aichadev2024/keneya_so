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


// Tableaux avec en-tête : sur téléphone, chaque ligne s'affiche comme une carte
// (voir .table-cards dans app.css). On recopie ici le libellé de colonne dans
// chaque cellule ; les tableaux sans en-tête (clé/valeur) restent inchangés.
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".table-responsive > table.table").forEach(function (table) {
    var entetes = table.querySelectorAll("thead th");
    if (!entetes.length || table.classList.contains("no-cards")) return;
    var libelles = Array.prototype.map.call(entetes, function (th) { return th.textContent.trim(); });
    table.querySelectorAll("tbody tr").forEach(function (ligne) {
      var i = 0;
      Array.prototype.forEach.call(ligne.children, function (cellule) {
        if (cellule.tagName !== "TD") return;
        cellule.setAttribute("data-label", libelles[i] || "");
        i += cellule.colSpan || 1;
      });
    });
    table.classList.add("table-cards");
  });
});
