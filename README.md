# Veille IA

Liens et textes intéressants sur l'IA, triés par dossier.

**Site : https://david-bouyssel.github.io/veille-ia/**. Parcourez l'arborescence, cochez des dossiers ou des liens, puis téléchargez un fichier de favoris à importer dans Firefox, Chrome, Edge, Opera, Brave, Vivaldi ou Safari.

## Fonctionnement

```
Firefox 1 ⇄ Floccus ⇄ ce dépôt (bookmarks.xbel + textes/) ⇄ Floccus ⇄ Firefox 2
                              │
                     GitHub Action « Publier »
                              ├─ site : arborescence, recherche, export à la carte
                              ├─ exports/tout.html : tous les favoris
                              └─ exports/<dossier>.html : un fichier par dossier
```

- `bookmarks.xbel` : écrit par Floccus. C'est la source de vérité, ne pas l'éditer à la main pendant qu'une synchro tourne.
- `textes/*.md` : vos citations et notes, rattachées à un favori par son URL.
- `config.json` : titre, description, lien du dépôt, nom du fichier de favoris.
- `scripts/build.py` : génère le site (Python 3, bibliothèque standard uniquement).
- `site/` : la page web (HTML, CSS, JS sans dépendance).
- `exemple/bookmarks.xbel` : données d'exemple, utilisées tant que `bookmarks.xbel` n'existe pas.

## Mise en place

### 1. Le dépôt

1. Poussez ce dossier dans un nouveau dépôt GitHub **public**, par exemple `veille-ia`, branche `main`.
2. Dans le dépôt : **Settings → Pages → Build and deployment → Source : GitHub Actions**.
3. Si vous forkez ce dépôt, remplacez `david-bouyssel` par votre compte dans `config.json` et dans ce README.
4. Onglet **Actions** : le workflow « Publier » tourne et publie le site avec les données d'exemple.

### 2. Le token pour Floccus

**Settings du compte → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token** :

- *Repository access* : **Only select repositories** → `veille-ia` uniquement.
- *Permissions* : **Contents : Read and write**. Rien d'autre.
- Choisissez une date d'expiration et notez-la.

> ⚠️ Ce token donne accès en écriture au dépôt. Ne le partagez pas, ne le mettez jamais dans un fichier du dépôt.

### 3. Floccus dans chaque Firefox

Installez [Floccus](https://addons.mozilla.org/firefox/addon/floccus/), puis **Ajouter un profil → Git** :

| Champ | Valeur |
|---|---|
| URL du dépôt | `https://github.com/david-bouyssel/veille-ia.git` |
| Branche | `main` |
| Fichier | `bookmarks.xbel` (à la racine) |
| Utilisateur | votre identifiant GitHub |
| Mot de passe | le token de l'étape 2 |
| Dossier local | votre dossier de favoris `IA` uniquement |

Faites la même chose sur le second Firefox, avec le même dépôt, la même branche et le même fichier. Floccus fusionne les ajouts des deux côtés.

> ⚠️ **Tout ce que Floccus synchronise devient public.** Pointez-le sur le seul dossier `IA`, jamais sur la racine de vos favoris.

Si votre version de Floccus écrit du HTML plutôt que du XBEL, changez `"source"` dans `config.json` (par exemple `bookmarks.html`). Le script reconnaît les deux formats.

### 4. Organiser

- Les **sous-dossiers** du dossier `IA` deviennent les catégories du site, à toute profondeur.
- La **description** d'un favori (si votre navigateur ou Floccus la conserve) s'affiche sous le lien.
- Pour un **texte** ou une citation, créez `textes/un-nom.md` (via l'interface GitHub, bouton *Add file*) :

  ```markdown
  ---
  url: https://adresse-exacte-du-favori
  titre: À retenir
  date: 2026-11-10
  ---
  Votre note.

  > Une citation, en commençant la ligne par >.
  ```

  Le texte s'attache au favori de même URL. Sans favori correspondant, il apparaît dans « Textes sans favori ».

## Récupérer les favoris (pour tout le monde)

- **À la carte** : sur le site, cochez puis *Télécharger la sélection*.
- **Un dossier entier** : lien *↓ .html* à côté de chaque dossier.
- **Tout** : `https://david-bouyssel.github.io/veille-ia/exports/tout.html`.

Puis importez le fichier dans le navigateur. Les instructions par navigateur sont en bas du site. L'import crée un dossier séparé et ne touche pas aux favoris existants.

Pour suivre les mises à jour automatiquement, il faut Floccus : faites un *fork* du dépôt avec votre propre token, et choisissez la stratégie de synchro à sens unique (« toujours annuler les changements locaux »). La lecture d'un dépôt public sans token n'est pas documentée par Floccus.

## Tester en local

```bash
python scripts/build.py --out _site
python -m http.server 8000 --directory _site
```

Puis ouvrez http://localhost:8000.
