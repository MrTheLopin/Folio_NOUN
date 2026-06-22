/* ===========================================================
   sidebar.js — injecte la navigation latérale partagée
   Détecte la page courante via le nom de fichier dans l'URL.
=========================================================== */
(function(){
  const NAV_ITEMS = [
    { href: "index.html",       label: "Accueil" },
    { href: "trade_log.html",   label: "Détail des trades" },
    { href: "journal.html",     label: "Journal de bord", featured: true },
    { href: "backtest_results.png", label: "Dernier graphique" },
    { href: "commandes.html",   label: "Liste de commandes" },
    { href: "changelog.html",   label: "Suivi changement" },
  ];

  const currentFile = window.location.pathname.split("/").pop() || "index.html";

  const navHtml = NAV_ITEMS.map(item => {
    const isActive = item.href === currentFile;
    const featClass = item.featured ? " sb-featured" : "";
    const activeClass = isActive ? " active" : "";
    return `<a href="${item.href}" class="${featClass}${activeClass}"><span class="sb-dot"></span>${item.label}</a>`;
  }).join("");

  const sidebarHtml = `
    <div class="sb-brand"><b>Signal/Croisement</b>bot de trading BTC/USDT</div>
    <nav>${navHtml}</nav>
    <div class="sb-footer">Projet éducatif — testnet uniquement.</div>
  `;

  const container = document.createElement("div");
  container.id = "siteSidebar";
  container.innerHTML = sidebarHtml;
  document.body.insertBefore(container, document.body.firstChild);
})();
