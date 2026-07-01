# 03 — BONUS : sécuriser la *supply chain* de l'image

> **Suite du [README](README.md).** Une fois la stack durcie (réseaux, non-root, secrets), on
> s'occupe de l'**image elle-même** : est-elle **bien configurée**, **sans secret oublié**, **sans
> vulnérabilité connue**, et **authentique** ? On suit l'ordre d'un vrai pipeline :

```
       AVANT le build                    APRÈS le build              APRÈS validation
  ┌───────────────────────┐        ┌────────────────────┐        ┌──────────────────┐
  │ §9  SAST : conf +      │        │  (build de l'image)│        │ §10  SIGNATURE   │
  │      secrets + deps    │  --->  │   §9b scan de l'    │  --->  │   Cosign/Sigstore│
  │  (analyse statique)    │        │        image       │        │ (intégrité/origine)│
  └───────────────────────┘        └────────────────────┘        └──────────────────┘
```

> 💡 **L'idée directrice :** on **échoue tôt** (SAST/secrets sur le code, avant même de builder),
> on **scanne** l'image produite, et on ne **signe** qu'une image jugée saine. On ne signe jamais
> une image qu'on n'a pas d'abord vérifiée.

---

## 🔎 §9 — Analyse statique : configuration, secrets & vulnérabilités

**Analyse statique (SAST)** = inspecter le code / les fichiers **sans exécuter** l'application.
Pour une image Docker, trois choses valent le coup d'œil **avant** de construire :

| Cible | Ce qu'on cherche | Exemple de finding |
|---|---|---|
| **Configuration** (Dockerfile, compose) | mauvaises pratiques / durcissement manquant | `USER root`, pas de `HEALTHCHECK`, port en clair… |
| **Secrets** | mots de passe / tokens **oubliés** dans les fichiers | une clé AWS commitée, un `.env` non ignoré |
| **Dépendances** (requirements.txt…) | librairies avec **CVE** connues | `flask==2.0.0` avec une faille connue |

### Deux approches possibles

| Approche | Outils | Idée |
|---|---|---|
| **Outils dédiés** | `hadolint` (lint Dockerfile) + `gitleaks` (secrets) + `trivy`/`grype` (vuln) | chaque outil spécialisé, très fin — proche d'un vrai pipeline multi-étapes |
| **Tout-en-un** | **`trivy`** seul | config + secrets + vulnérabilités dans **un** outil — plus simple à démarrer |

👉 **Dans ce lab, on se base sur Trivy** (tout-en-un). On le lance **via son conteneur** (rien à
installer), à la racine de `03-better-compose/`.

```bash
# alias pratique : trivy dans un conteneur, avec accès au dossier courant
trivy() { docker run --rm -v "$PWD:/w" -w /w aquasec/trivy:0.66.0 "$@"; }
```

🚧 **À compléter :** lancez les trois analyses statiques (elles portent sur les **fichiers**, pas
sur une image — donc **avant** le build).

```bash
# 1) MISCONFIG : audite Dockerfile / compose (durcissement, bonnes pratiques)
trivy config .

# 2) SECRETS : cherche des secrets oubliés dans les fichiers du dossier
trivy fs --scanners secret .

# 3) VULNÉRABILITÉS des dépendances : lit requirements.txt et signale les CVE
trivy fs --scanners vuln .
```

> 💡 *Pourquoi avant le build ?* Ces problèmes vivent dans le **code source** (Dockerfile,
> requirements, fichiers du repo). Les détecter **avant** de construire, c'est **échouer vite** et
> ne pas gaspiller un build sur une base déjà cassée.

> 🧪 **Voir un vrai résultat :** avec des dépendances récentes, le scan vuln peut être vide (tant
> mieux !). Pour **provoquer** une détection et comprendre la sortie, épinglez temporairement une
> **vieille** version dans `requirements.txt` :
> ```bash
> printf 'flask==2.0.0\nredis==4.0.0\n' > requirements.txt
> trivy fs --scanners vuln .        # -> CVE-2023-30861 (HIGH) sur flask, avec la version corrigée
> ```
> …puis **remettez** `flask` / `redis` sans version (ou à jour). De même pour les secrets :
> `trivy fs --scanners secret .` sur un fichier contenant un faux token `ghp_…` le détecte
> (CRITICAL).

> ⚠️ **Attention aux faux positifs / au bruit :** `trivy config` peut remonter des règles non
> pertinentes pour un lab. On peut **filtrer par sévérité** et **ignorer** des règles :
> ```bash
> trivy config --severity HIGH,CRITICAL .           # ne garder que le sérieux
> trivy fs --scanners vuln --ignore-unfixed .        # cacher les CVE sans correctif dispo
> ```

> 📖 [Trivy — misconfiguration](https://trivy.dev/latest/docs/scanner/misconfiguration/) ·
> [secret scanning](https://trivy.dev/latest/docs/scanner/secret/) ·
> [vulnerabilities](https://trivy.dev/latest/docs/scanner/vulnerability/)

### §9b (optionnel) — scanner l'**image** une fois buildée

Les scans ci-dessus portent sur le **source**. Une fois l'image **construite**, on peut aussi
scanner ses **couches** (paquets de l'OS de base + libs installées) — c'est là qu'on voit les CVE
du système, pas seulement des dépendances Python.

```bash
docker build -t myapp:dev .                          # (si pas déjà fait)
trivy image --severity HIGH,CRITICAL myapp:dev       # scan des couches de l'image
```

> 💡 *Trivy vs Grype ?* Ce sont deux scanners de vulnérabilités équivalents pour cet usage
> (`grype myapp:dev` ferait la même chose). On reste sur **Trivy** ici, mais c'est le **même
> réflexe** : scanner l'image **avant** de la promouvoir/signer.

---

## ✍️ §10 — Signer l'image avec **Cosign / Sigstore**

Le scan (§9) nous dit que l'image est **saine**. Reste : **cette image, d'où vient-elle et est-elle
intègre ?** Signer l'image répond à ça — au déploiement, on **vérifie** qu'elle a bien été produite
par nous et qu'elle n'a pas été altérée. **On ne signe qu'une image déjà scannée.**

> ℹ️ On signe **un digest** (`myapp@sha256:…`), pas un tag. Un tag (`:dev`) est **mutable** — il
> peut être re-poussé sur un autre contenu. Le digest, lui, **identifie le contenu** de façon
> unique : c'est *ça* qu'on garantit.

### Deux niveaux d'usage de Cosign

Cosign (le CLI du projet **Sigstore**) s'utilise à deux niveaux — commencez par le premier :

| Niveau | Comment | Ce que ça demande |
|---|---|---|
| **1. Key-based** (simple) | une **paire de clés** cosign locale (`cosign.key` / `cosign.pub`) | juste un registre où pousser la signature |
| **2. Keyless** (Sigstore complet) | **pas de clé longue durée** : une identité **OIDC** (GitHub, Google…) + certificat éphémère **Fulcio** + journal de transparence **Rekor** | un flux OIDC (typiquement en **CI**) |

Le keyless est l'approche **recommandée en prod/CI** (pas de clé à garder au chaud, tout est
tracé publiquement). Mais pour **comprendre** et travailler en local, on fait le **key-based**.

### Niveau 1 — signature key-based (mode simple)

On utilise Cosign **via son conteneur** (rien à installer). On travaille sur un **registre local**
pour rester autonome (pas besoin de Docker Hub). Deux options selon ce que vous voulez :

| Option | Registre | Pour quoi |
|---|---|---|
| **A — simple** | `registry:2` (1 conteneur, sans UI) | aller vite, juste push/pull/signer |
| **B — avec UI** | `registry:2` + une UI web (dossier [`registry-ui/`](registry-ui/)) | **voir** images / tags / digests / signatures dans un navigateur |

> 🏢 *Et en entreprise ?* On utilise un vrai registre managé — **Harbor** ou **Quay** — qui
> ajoutent RBAC, scan de vulnérabilités **intégré**, réplication, quotas… Ils sont **bien plus
> lourds** (Harbor ≈ 9 conteneurs ; Quay = quay + Postgres + Redis + un `config.yaml`), donc
> **hors-scope** pour ce lab local. Le principe cosign, lui, est **identique** quel que soit le
> registre.

**Option A — registre minimal :**

```bash
# 0) un registre local jetable (port 5000) + on y pousse notre image
docker run -d --name registry -p 127.0.0.1:5000:5000 registry:2
docker tag myapp:dev 127.0.0.1:5000/myapp:dev
docker push 127.0.0.1:5000/myapp:dev
```

**Option B — registre + UI** (on vous fournit le compose, à copier tel quel) :

```bash
# démarrer le registre AVEC son interface web
cd registry-ui && docker compose up -d && cd ..
#   push/pull : 127.0.0.1:5000     UI : http://localhost:8085
docker tag myapp:dev 127.0.0.1:5000/myapp:dev
docker push 127.0.0.1:5000/myapp:dev
# -> ouvrez http://localhost:8085 : vous VOYEZ le repo "myapp", son tag "dev" et son digest.
#    Après la signature (ci-dessous), un second "tag" .sig apparaîtra = la signature cosign.
```

La suite (signer / vérifier) est **identique** quelle que soit l'option choisie.

```bash
# alias pratique : cosign dans un conteneur, avec accès au registre de l'hôte.
# COSIGN_PASSWORD = la passphrase de la clé (évite les prompts interactifs dans le conteneur).
cosign() { docker run --rm --network host -e COSIGN_PASSWORD -v "$PWD:/w" -w /w \
  gcr.io/projectsigstore/cosign:v2.4.1 "$@"; }
export COSIGN_PASSWORD="ma-passphrase"    # choisissez-la ; en prod, pas en clair !
```

🚧 **À compléter :** générez la paire de clés, signez le **digest**, puis vérifiez.

```bash
# 1) générer la paire de clés (utilise COSIGN_PASSWORD)
cosign generate-key-pair                 # -> cosign.key (PRIVÉE, à NE PAS committer) + cosign.pub

# 2) SIGNER l'image (cosign résout le tag -> digest et signe le digest)
#    --yes : accepte sans prompt la journalisation dans le log de transparence (voir note)
cosign sign --yes --key cosign.key 127.0.0.1:5000/myapp:dev

# 3) VÉRIFIER avec la clé publique
cosign verify --key cosign.pub 127.0.0.1:5000/myapp:dev     # -> "...were verified..." ✅
```

> 🔒 **`cosign.key` est un secret** : il est déjà dans le `.gitignore` (comme les mots de passe des
> §6–§8). Seule **`cosign.pub`** se partage/commit. *(Bonus : stocker `cosign.key` dans le
> HashiCorp Vault du §8 — la boucle est bouclée.)*
>
> ℹ️ **Même en key-based, Cosign journalise la signature dans Rekor** (le log de transparence
> **public** de Sigstore) par défaut — d'où le `--yes`. Pour un lab **100 % local/privé**, on peut
> désactiver ce log : `cosign sign --tlog-upload=false …` (et `--insecure-ignore-tlog` à la vérif).
>
> 💡 **Tester l'altération :** re-poussez une **image différente** sur le **même tag**, puis
> relancez `cosign verify` → il **échoue** (`no signatures found` : le nouveau digest n'est pas
> signé). C'est tout l'intérêt — la signature suit le **contenu**, pas le tag.

### Niveau 2 — signature keyless (pour aller plus loin)

En CI, on ne garde **aucune clé**. Cosign génère une clé **éphémère** en mémoire, obtient un
certificat court (**Fulcio**) lié à votre **identité OIDC**, journalise la signature dans
**Rekor**, et jette la clé. À la vérif, on ne fournit pas de `.pub` mais **l'identité attendue** :

```bash
# signer (déclenche un login OIDC ; en CI, l'identité vient du pipeline)
cosign sign 127.0.0.1:5000/myapp@sha256:...

# vérifier une IDENTITÉ, pas une clé
cosign verify 127.0.0.1:5000/myapp@sha256:... \
  --certificate-identity="you@example.com" \
  --certificate-oidc-issuer="https://accounts.google.com"
```

> 📖 [Cosign — signing containers](https://docs.sigstore.dev/cosign/signing/signing_with_containers/) ·
> [verifying signatures](https://docs.sigstore.dev/cosign/verifying/verify/) ·
> [keyless overview](https://docs.sigstore.dev/cosign/signing/overview/)
>
> 💡 *À retenir :* key-based = **une clé à protéger** ; keyless = **une identité à protéger** (plus
> de secret longue durée, tout est tracé dans Rekor). En vrai pipeline (04 / GitOps), c'est le
> keyless qu'on branche.

> 🧹 **Nettoyage :** option A → `docker rm -f registry` ; option B → `cd registry-ui && docker
> compose down -v`.

---

## 🎉 Récap BONUS

- [ ] **SAST** avec Trivy : `config` (misconfig), `fs --scanners secret`, `fs --scanners vuln`.
- [ ] (optionnel) Scan de l'**image** buildée (`trivy image`) — ou `grype`.
- [ ] Image poussée sur un **registre local** (option A `registry:2`, ou option B avec **UI**).
- [ ] Image **signée** avec Cosign (key-based) et **vérifiée** (`Verified OK`).
- [ ] Compris l'ordre : **SAST → build → scan image → signature** (échouer tôt, ne signer que le sain).
