"use strict";

// Arborescence chargée depuis data.json (généré par scripts/build.py).
let donnees = null;
const liensParId = new Map();      // id -> noeud lien
const elementsLien = new Map();    // id -> <div class="lien">
const dossiersUI = [];             // { noeud, details, case, ids: [ids des liens descendants] }
const selection = new Set();

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...enfants) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const enf of enfants) if (enf) e.append(enf);
  return e;
}

function urlSure(url) {
  return /^https?:\/\//i.test(url) ? url : null;
}

function hote(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return ""; }
}

// ------------------------------------------------------------------ rendu

function rendreTexte(corps) {
  const bloc = el("div", { class: "texte-corps" });
  for (const para of corps.split(/\n\s*\n/)) {
    const lignes = para.split("\n");
    if (lignes.every((l) => l.trimStart().startsWith(">"))) {
      bloc.append(el("blockquote", { text: lignes.map((l) => l.replace(/^\s*>\s?/, "")).join("\n") }));
    } else if (para.trim()) {
      bloc.append(el("p", { text: para.trim() }));
    }
  }
  return bloc;
}

function rendreLien(noeud) {
  const id = noeud._id;
  const caseCoche = el("input", { type: "checkbox", "aria-label": `Sélectionner ${noeud.titre}` });
  caseCoche.addEventListener("change", () => {
    caseCoche.checked ? selection.add(id) : selection.delete(id);
    majEtat();
  });
  noeud._case = caseCoche;

  const href = urlSure(noeud.url);
  const titre = href
    ? el("a", { class: "lien-titre", href, target: "_blank", rel: "noopener noreferrer", text: noeud.titre })
    : el("span", { class: "lien-titre", text: noeud.titre });

  const corps = el("div", { class: "lien-corps" }, titre, el("span", { class: "hote", text: hote(noeud.url) }));
  if (noeud.desc) corps.append(el("p", { class: "lien-desc", text: noeud.desc }));
  for (const t of noeud.textes || []) {
    const libelle = [t.titre || "Texte", t.date].filter(Boolean).join(" · ");
    corps.append(el("details", { class: "texte" }, el("summary", { text: libelle }), rendreTexte(t.corps)));
  }

  const div = el("div", { class: "lien" }, caseCoche, corps);
  elementsLien.set(id, div);
  return div;
}

function rendreDossier(noeud) {
  const caseCoche = el("input", { type: "checkbox", "aria-label": `Sélectionner le dossier ${noeud.titre}` });
  const ids = [];
  const contenu = el("div", { class: "contenu" });
  for (const e of noeud.enfants) {
    if (e.type === "dossier") {
      const sous = rendreDossier(e);
      contenu.append(sous.details);
      ids.push(...sous.ids);
    } else {
      contenu.append(rendreLien(e));
      ids.push(e._id);
    }
  }

  const resume = el(
    "summary", {},
    caseCoche,
    el("span", { class: "nom-dossier", text: noeud.titre }),
    el("span", { class: "compte", text: `(${noeud.nb})` }),
    el("a", { class: "export", href: noeud.export, download: `${noeud.slug}.html`, text: "↓ .html",
              title: `Télécharger « ${noeud.titre} » au format favoris` }),
  );
  const details = el("details", { class: "dossier", open: true }, resume, contenu);

  const ui = { noeud, details, case: caseCoche, ids };
  caseCoche.addEventListener("change", () => {
    for (const id of ids) {
      if (elementsLien.get(id).hidden) continue;
      caseCoche.checked ? selection.add(id) : selection.delete(id);
    }
    majEtat();
  });
  dossiersUI.push(ui);
  return ui;
}

function numeroter(noeud, compteur = { n: 0 }) {
  for (const e of noeud.enfants) {
    if (e.type === "dossier") numeroter(e, compteur);
    else { e._id = compteur.n++; liensParId.set(e._id, e); }
  }
}

// ------------------------------------------------------------------ état

function majEtat() {
  for (const [id, noeud] of liensParId) noeud._case.checked = selection.has(id);
  for (const ui of dossiersUI) {
    const nb = ui.ids.filter((id) => selection.has(id)).length;
    ui.case.checked = nb > 0 && nb === ui.ids.length;
    ui.case.indeterminate = nb > 0 && nb < ui.ids.length;
  }
  const bouton = $("telecharger");
  bouton.disabled = selection.size === 0;
  bouton.textContent = selection.size
    ? `Télécharger la sélection (${selection.size})`
    : "Télécharger la sélection";
}

function filtrer(requete) {
  const q = requete.trim().toLowerCase();
  for (const [id, noeud] of liensParId) {
    const cible = [noeud.titre, noeud.url, noeud.desc, ...(noeud.textes || []).map((t) => t.corps)]
      .join(" ").toLowerCase();
    elementsLien.get(id).hidden = q !== "" && !cible.includes(q);
  }
  for (const ui of dossiersUI) {
    const visible = ui.ids.some((id) => !elementsLien.get(id).hidden);
    ui.details.hidden = !visible;
    if (q) ui.details.open = true;
  }
}

// ------------------------------------------------------------------ export

const echapper = (s) => String(s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function netscape(titre, noeud) {
  const lignes = [
    "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
    '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
    `<TITLE>${echapper(titre)}</TITLE>`,
    `<H1>${echapper(titre)}</H1>`,
    "<DL><p>",
  ];
  const bloc = (d, nom, prof) => {
    const ind = "    ".repeat(prof);
    lignes.push(`${ind}<DT><H3>${echapper(nom)}</H3>`, `${ind}<DL><p>`);
    for (const e of d.enfants) {
      if (e.type === "dossier") bloc(e, e.titre, prof + 1);
      else {
        const date = e.ajout ? ` ADD_DATE="${e.ajout}"` : "";
        lignes.push(`${ind}    <DT><A HREF="${echapper(e.url)}"${date}>${echapper(e.titre)}</A>`);
        if (e.desc) lignes.push(`${ind}    <DD>${echapper(e.desc)}`);
      }
    }
    lignes.push(`${ind}</DL><p>`);
  };
  bloc(noeud, titre, 1);
  lignes.push("</DL><p>");
  return lignes.join("\n") + "\n";
}

// Copie de l'arbre réduite aux liens cochés ; les dossiers vides disparaissent.
function elaguer(noeud) {
  const enfants = [];
  for (const e of noeud.enfants) {
    if (e.type === "dossier") {
      const sous = elaguer(e);
      if (sous.enfants.length) enfants.push(sous);
    } else if (selection.has(e._id)) {
      enfants.push(e);
    }
  }
  return { ...noeud, enfants };
}

function telecharger() {
  const contenu = netscape(donnees.titre, elaguer(donnees.racine));
  const blob = new Blob([contenu], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = el("a", { href: url, download: "veille-ia-selection.html" });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ------------------------------------------------------------------ démarrage

async function demarrer() {
  try {
    const rep = await fetch("data.json", { cache: "no-cache" });
    if (!rep.ok) throw new Error(`HTTP ${rep.status}`);
    donnees = await rep.json();
  } catch (err) {
    $("arbre").replaceChildren(el("p", { class: "vide", text: `Impossible de charger data.json (${err.message}).` }));
    return;
  }

  document.title = donnees.titre;
  $("titre").textContent = donnees.titre;
  $("description").textContent = donnees.description || "";
  $("bandeau-exemple").hidden = !donnees.exemple;

  const date = new Date(donnees.genere).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
  const meta = $("meta");
  meta.append(`${donnees.racine.nb} liens · mis à jour le ${date} · `);
  meta.append(el("a", { href: donnees.racine.export, download: "veille-ia.html", text: "tout télécharger (.html)" }));
  if (urlSure(donnees.depot || "")) {
    meta.append(" · ", el("a", { href: donnees.depot, text: "dépôt GitHub" }));
  }

  numeroter(donnees.racine);
  const arbre = $("arbre");
  arbre.replaceChildren();
  for (const e of donnees.racine.enfants) {
    arbre.append(e.type === "dossier" ? rendreDossier(e).details : rendreLien(e));
  }
  if (!liensParId.size) arbre.append(el("p", { class: "vide", text: "Aucun lien pour l'instant." }));

  $("recherche").addEventListener("input", (ev) => filtrer(ev.target.value));
  $("tout").addEventListener("click", () => {
    for (const [id] of liensParId) if (!elementsLien.get(id).hidden) selection.add(id);
    majEtat();
  });
  $("rien").addEventListener("click", () => { selection.clear(); majEtat(); });
  $("telecharger").addEventListener("click", telecharger);
  majEtat();
}

demarrer();
