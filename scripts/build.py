#!/usr/bin/env python3
"""Construit le site GitHub Pages à partir du fichier de favoris synchronisé par Floccus.

Entrées :
  - config.json            titre, description, chemin du fichier de favoris
  - <source>               fichier XBEL ou HTML Netscape (format détecté automatiquement)
  - textes/*.md            citations / notes rattachées à un lien par leur URL

Sorties (dans --out) :
  - index.html, app.js, style.css   copiés depuis site/
  - data.json                       arborescence complète pour le site
  - exports/tout.html               tous les favoris, importables dans n'importe quel navigateur
  - exports/<dossier>.html          un fichier par dossier (et sous-dossier)

Uniquement la bibliothèque standard de Python 3.9+.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

RACINE_DEPOT = Path(__file__).resolve().parent.parent
SOURCE_EXEMPLE = "exemple/bookmarks.xbel"
SCHEMAS_AUTORISES = ("http://", "https://")


def avertir(message: str) -> None:
    print(f"::warning::{message}", file=sys.stderr)


# --------------------------------------------------------------------------- modèle


def dossier(titre: str) -> dict:
    return {"type": "dossier", "titre": titre.strip() or "Sans titre", "enfants": []}


def lien(titre: str, url: str, desc: str = "", ajout: int | None = None) -> dict:
    return {
        "type": "lien",
        "titre": titre.strip() or url,
        "url": url.strip(),
        "desc": desc.strip(),
        "ajout": ajout,
        "textes": [],
    }


def date_en_epoch(valeur: str | None) -> int | None:
    """XBEL utilise des dates ISO 8601, le HTML Netscape des secondes (ou microsecondes)."""
    if not valeur:
        return None
    valeur = valeur.strip()
    if valeur.isdigit():
        n = int(valeur)
        return n // 1_000_000 if n > 10_000_000_000 else n
    try:
        d = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(d.timestamp())


# --------------------------------------------------------------------------- lecture XBEL


def lire_xbel(texte: str) -> dict:
    racine_xml = ET.fromstring(texte)
    racine = dossier("racine")

    def parcourir(element: ET.Element, cible: dict) -> None:
        for enfant in element:
            if enfant.tag == "folder":
                d = dossier(enfant.findtext("title") or "")
                parcourir(enfant, d)
                cible["enfants"].append(d)
            elif enfant.tag == "bookmark":
                cible["enfants"].append(
                    lien(
                        enfant.findtext("title") or "",
                        enfant.get("href", ""),
                        enfant.findtext("desc") or "",
                        date_en_epoch(enfant.get("added")),
                    )
                )

    parcourir(racine_xml, racine)
    return racine


# --------------------------------------------------------------------------- lecture HTML Netscape


class LecteurNetscape(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.racine = dossier("racine")
        self.pile: list[dict] = [self.racine]
        self.dl_ouverts = 0
        self.dossier_en_attente: dict | None = None
        self.capture: str | None = None  # "h3", "a" ou "dd"
        self.tampon: list[str] = []
        self.lien_courant: dict | None = None
        self.dernier_element: dict | None = None

    def _fermer_capture(self) -> None:
        texte = "".join(self.tampon).strip()
        if self.capture == "h3":
            d = dossier(texte)
            self.pile[-1]["enfants"].append(d)
            self.dossier_en_attente = d
            self.dernier_element = d
        elif self.capture == "a" and self.lien_courant is not None:
            self.lien_courant["titre"] = texte or self.lien_courant["url"]
            self.pile[-1]["enfants"].append(self.lien_courant)
            self.dernier_element = self.lien_courant
            self.lien_courant = None
        elif self.capture == "dd" and self.dernier_element is not None and texte:
            if self.dernier_element["type"] == "lien":
                self.dernier_element["desc"] = texte
        self.capture = None
        self.tampon = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if self.capture == "dd" and tag in ("dt", "dl"):
            self._fermer_capture()
        if tag == "dl":
            self.dl_ouverts += 1
            if self.dossier_en_attente is not None:
                self.pile.append(self.dossier_en_attente)
                self.dossier_en_attente = None
        elif tag == "h3":
            self.capture, self.tampon = "h3", []
        elif tag == "a":
            self.lien_courant = lien("", a.get("href", ""), "", date_en_epoch(a.get("add_date")))
            self.capture, self.tampon = "a", []
        elif tag == "dd":
            self.capture, self.tampon = "dd", []

    def handle_endtag(self, tag):
        if tag in ("h3", "a") and self.capture == tag:
            self._fermer_capture()
        elif tag == "dl":
            if self.capture == "dd":
                self._fermer_capture()
            self.dl_ouverts -= 1
            if len(self.pile) > 1:
                self.pile.pop()

    def handle_data(self, data):
        if self.capture:
            self.tampon.append(data)


def lire_netscape(texte: str) -> dict:
    lecteur = LecteurNetscape()
    lecteur.feed(texte)
    lecteur.close()
    return lecteur.racine


def lire_source(chemin: Path) -> dict:
    texte = chemin.read_text(encoding="utf-8-sig")
    if re.search(r"<xbel[\s>]", texte[:4000], re.IGNORECASE):
        return lire_xbel(texte)
    return lire_netscape(texte)


# --------------------------------------------------------------------------- textes


def normaliser_url(url: str) -> str:
    url = url.strip().split("#", 1)[0]
    url = re.sub(r"^https?://(www\.)?", "", url, flags=re.IGNORECASE)
    return url.rstrip("/").lower()


def lire_texte(chemin: Path) -> dict | None:
    brut = chemin.read_text(encoding="utf-8-sig")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", brut, re.DOTALL)
    if not m:
        avertir(f"{chemin.name} : en-tête --- manquant, fichier ignoré")
        return None
    meta = {}
    for ligne in m.group(1).splitlines():
        if ":" in ligne:
            cle, valeur = ligne.split(":", 1)
            meta[cle.strip().lower()] = valeur.strip().strip('"').strip("'")
    if not meta.get("url"):
        avertir(f"{chemin.name} : champ url manquant, fichier ignoré")
        return None
    return {
        "fichier": chemin.name,
        "url": meta["url"],
        "titre": meta.get("titre", ""),
        "date": meta.get("date", ""),
        "corps": m.group(2).strip(),
    }


def rattacher_textes(racine: dict, dossier_textes: Path) -> None:
    if not dossier_textes.is_dir():
        return
    index: dict[str, list[dict]] = {}

    def indexer(n: dict) -> None:
        for e in n["enfants"]:
            if e["type"] == "dossier":
                indexer(e)
            else:
                index.setdefault(normaliser_url(e["url"]), []).append(e)

    indexer(racine)
    orphelins = []
    for chemin in sorted(dossier_textes.glob("*.md")):
        t = lire_texte(chemin)
        if t is None:
            continue
        cibles = index.get(normaliser_url(t["url"]))
        if cibles:
            for c in cibles:
                c["textes"].append({k: t[k] for k in ("titre", "date", "corps")})
        else:
            orphelins.append(t)

    if orphelins:
        d = dossier("Textes sans favori")
        for t in orphelins:
            avertir(f"{t['fichier']} : aucun favori avec l'URL {t['url']}, placé dans « Textes sans favori »")
            l = lien(t["titre"] or t["url"], t["url"])
            l["textes"].append({k: t[k] for k in ("titre", "date", "corps")})
            d["enfants"].append(l)
        racine["enfants"].append(d)


# --------------------------------------------------------------------------- nettoyage, slugs, comptes


def nettoyer(n: dict) -> None:
    """Retire les liens non http(s) (bookmarklets javascript:, place:, etc.)."""
    gardes = []
    for e in n["enfants"]:
        if e["type"] == "dossier":
            nettoyer(e)
            gardes.append(e)
        elif e["url"].lower().startswith(SCHEMAS_AUTORISES):
            gardes.append(e)
        else:
            avertir(f"lien ignoré (schéma non http/https) : {e['titre']} -> {e['url'][:60]}")
    n["enfants"] = gardes


def slugifier(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "dossier"


def annoter(n: dict, chemin: list[str], slugs_pris: set[str]) -> int:
    """Ajoute chemin, slug, fichier d'export et nombre de liens à chaque dossier."""
    total = 0
    for e in n["enfants"]:
        if e["type"] == "dossier":
            sous_chemin = chemin + [e["titre"]]
            base = "--".join(slugifier(p) for p in sous_chemin)
            slug, i = base, 2
            while slug in slugs_pris:
                slug, i = f"{base}-{i}", i + 1
            slugs_pris.add(slug)
            e["chemin"] = sous_chemin
            e["slug"] = slug
            e["export"] = f"exports/{slug}.html"
            total += annoter(e, sous_chemin, slugs_pris)
        else:
            total += 1
    n["nb"] = total
    return total


# --------------------------------------------------------------------------- export HTML Netscape


def ecrire_netscape(titre_dossier: str, n: dict) -> str:
    """Format reconnu par Firefox, Chrome, Edge, Opera, Brave, Vivaldi et Safari."""
    lignes = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        "<!-- Fichier généré automatiquement. Importez-le depuis le gestionnaire de favoris. -->",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        f"<TITLE>{html.escape(titre_dossier)}</TITLE>",
        f"<H1>{html.escape(titre_dossier)}</H1>",
        "<DL><p>",
    ]

    def bloc(d: dict, titre: str, profondeur: int) -> None:
        ind = "    " * profondeur
        lignes.append(f"{ind}<DT><H3>{html.escape(titre)}</H3>")
        lignes.append(f"{ind}<DL><p>")
        for e in d["enfants"]:
            if e["type"] == "dossier":
                bloc(e, e["titre"], profondeur + 1)
            else:
                date = f' ADD_DATE="{e["ajout"]}"' if e.get("ajout") else ""
                lignes.append(
                    f'{ind}    <DT><A HREF="{html.escape(e["url"], quote=True)}"{date}>{html.escape(e["titre"])}</A>'
                )
                if e["desc"]:
                    lignes.append(f"{ind}    <DD>{html.escape(e['desc'])}")
        lignes.append(f"{ind}</DL><p>")

    bloc(n, titre_dossier, 1)
    lignes.append("</DL><p>")
    return "\n".join(lignes) + "\n"


def exporter(n: dict, dossier_exports: Path) -> None:
    for e in n["enfants"]:
        if e["type"] == "dossier":
            (dossier_exports / f"{e['slug']}.html").write_text(
                ecrire_netscape(e["titre"], e), encoding="utf-8"
            )
            exporter(e, dossier_exports)


# --------------------------------------------------------------------------- principal


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(RACINE_DEPOT / "config.json"))
    p.add_argument("--out", default=str(RACINE_DEPOT / "_site"))
    args = p.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    titre = config.get("titre", "Veille IA")

    source = RACINE_DEPOT / config.get("source", "bookmarks.xbel")
    exemple = False
    if not source.is_file():
        avertir(f"{source.name} introuvable : utilisation des données d'exemple ({SOURCE_EXEMPLE})")
        source, exemple = RACINE_DEPOT / SOURCE_EXEMPLE, True

    racine = lire_source(source)
    rattacher_textes(racine, RACINE_DEPOT / config.get("textes", "textes"))
    nettoyer(racine)
    annoter(racine, [], set())
    racine["titre"] = titre
    racine["export"] = "exports/tout.html"

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(RACINE_DEPOT / "site", out)
    exports = out / "exports"
    exports.mkdir()
    (exports / "tout.html").write_text(ecrire_netscape(titre, racine), encoding="utf-8")
    exporter(racine, exports)

    donnees = {
        "titre": titre,
        "description": config.get("description", ""),
        "depot": config.get("depot", ""),
        "genere": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "exemple": exemple,
        "racine": racine,
    }
    (out / "data.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    nb_exports = len(list(exports.glob("*.html")))
    print(f"{racine['nb']} liens, {nb_exports} fichiers d'export -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
