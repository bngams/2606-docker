# 03 — Compose : bonnes pratiques, durcissement & secrets

Suite du **02 (Compose quickstart)**. La stack (Flask `web` + `redis`) est la même, mais on la
rend **propre et sûre** : réseaux segmentés, limites de ressources, durcissement sécurité,
robustesse, override de **prod**, et une progression sur les **secrets** (Compose → Ansible Vault
→ HashiCorp Vault).

## Arborescence

```
03-better-compose/
├── app.py  requirements.txt  Dockerfile   # l'app (Dockerfile avec USER appuser)
├── compose.yaml        # principal : include infra.yaml + service web (durci)
├── infra.yaml          # redis (durci) — inclus par compose.yaml
├── compose.prod.yaml   # override PROD : read_only, cap_drop, secrets
├── .env.example
├── secrets/            # secret réel gitignoré ; .sample fourni
└── ops/
    ├── ansible/deploy.yml          # déploiement avec secret via Ansible Vault
    └── vault/                      # exemples Ansible Vault + HashiCorp Vault
```

---

## Le menu des bonnes pratiques

### Réseau — segmentation
Deux réseaux **nommés** plutôt que le `default` :
- `web` est sur **`frontend`** (egress Internet) **+** `backend` ;
- `redis` est **uniquement** sur **`backend`** marqué **`internal: true`** → Redis n'a **aucun
  accès sortant** mais reste joignable par `web`. Surface d'attaque réduite, segmentation claire.

### Ressources — éviter qu'un conteneur tue l'hôte
`deploy.resources.limits` (**cpus + memory + pids**) est bien honoré par `docker compose up` en
**Compose v2** (contrairement à `replicas`/`reservations.cpus`, restés Swarm-only).
`pids: 200` protège des **fork bombs**. Sans limites, un conteneur peut **OOM** tout l'hôte.

> ⚠️ Mettre `pids` **dans `deploy.resources.limits.pids`** (pas un `pids_limit:` au même niveau
> que `deploy` → conflit "distinct values" en Compose v2).

### Sécurité
- **`no-new-privileges:true`** partout (bloque l'escalade via binaires setuid) ;
- port lié à **`127.0.0.1`** (pas `0.0.0.0`) si c'est local ;
- **`init: true`** (PID 1 propre : signaux + reaping des zombies) ;
- **logs plafonnés** (`max-size`/`max-file`) → évite le disque plein ;
- **utilisateur non-root** : `USER appuser` **dans le Dockerfile** (plus propre qu'un `user:` en
  compose, et ça **survit aux overrides**).

### Robustesse
- **`restart: unless-stopped`** ;
- image Redis **épinglée** (`7.4-alpine`, idéalement par **digest `@sha256:…`**) ;
- **persistance** Redis explicitée (`--appendonly yes`) ;
- **healthcheck** sur `web` (et `redis`).

---

## Lancer (dev)

```bash
cp .env.example .env
docker compose up --build              # compose.yaml inclut infra.yaml automatiquement
curl 127.0.0.1:8000                     # "Hello … seen N time(s)"
docker compose watch                    # hot-reload (develop.watch)
```

---

## Override de prod — `compose.prod.yaml`

```bash
docker compose -f compose.yaml -f compose.prod.yaml up -d
```

Durcissement : `read_only: true` + `tmpfs: [/tmp]`, `cap_drop`, secrets. **Deux pièges** à
connaître :

1. **`read_only` + `tmpfs` sur `web`** casse le sync de `develop.watch` vers `/code` (rootfs en
   lecture seule) → on le **réserve à la prod** (où il n'y a plus de watch ; d'où le
   `develop: !reset null` dans l'override).
2. **`cap_drop: [ALL]` sur `redis`** : l'entrypoint fait un `gosu redis` qui a besoin de
   **`CAP_SETUID` / `SETGID` / `CHOWN`**. Si on droppe tout, soit on **remet ces trois caps**
   (`cap_add`, ce qu'on fait), soit on lance directement `user: redis` (en s'assurant que le
   volume `redis-data` est déjà `chown redis`). **À tester — ce n'est pas plug-and-play.**

---

## Les secrets — progression en 3 niveaux

### Niveau 1 — Compose `secrets:` (fichier monté)

Plutôt qu'une **variable d'env** (visible dans `inspect`/`ps`), on monte un **fichier** et Redis
le lit. Redis n'ayant pas de `--requirepass-file`, on lit le secret **via un shell** :

```yaml
# compose.prod.yaml (extrait)
services:
  redis:
    command:
      - sh
      - -c
      - 'redis-server --appendonly yes --requirepass "$$(cat /run/secrets/redis_password)"'
    secrets: [redis_password]
secrets:
  redis_password:
    file: ./secrets/redis_password.txt   # fichier réel GITIGNORÉ (.sample fourni)
```

> **🧪 Manip :** `cp secrets/redis_password.txt.sample secrets/redis_password.txt`, puis
> `docker compose -f compose.yaml -f compose.prod.yaml up -d`. Vérifier que Redis exige le
> mot de passe : `docker compose exec redis redis-cli ping` → `NOAUTH` sans creds.

### Niveau 2 — Ansible Vault (chiffrer le secret **dans le repo**)

Le fichier secret en clair ne doit pas être commité. **Ansible Vault** le chiffre → commitable.
Voir [`ops/ansible/deploy.yml`](ops/ansible/deploy.yml) : le playbook **déchiffre** le mot de
passe au déploiement, écrit `secrets/redis_password.txt`, puis fait `compose up`.

```bash
cd ops/vault
cp secrets.vault.yml.sample secrets.vault.yml
ansible-vault encrypt secrets.vault.yml        # → commitable, chiffré
cd ../ansible
ansible-playbook deploy.yml --ask-vault-pass
```

### Niveau 3 — HashiCorp Vault (serveur centralisé)

Au lieu de stocker le secret (même chiffré) dans le repo, on le **lit à la demande** depuis un
**serveur Vault** (secrets dynamiques, rotation, audit). Voir
[`ops/vault/hashicorp-vault-example.md`](ops/vault/hashicorp-vault-example.md).

| | **Compose secrets** | **Ansible Vault** | **HashiCorp Vault** |
|---|---|---|---|
| Le secret… | fichier local gitignoré | **chiffré dans le repo** | sur un **serveur** |
| Dynamique / rotation | non | non | **oui** (TTL, génération) |
| Échelle | un projet | un projet | **organisation** |

---

## Recap

- **Réseaux** segmentés (`frontend` / `backend internal`), **ressources** limitées (cpu/mem/pids),
  **sécurité** (`no-new-privileges`, loopback, non-root via Dockerfile), **robustesse**
  (restart, image épinglée, persistance, healthcheck).
- **`include:`** sépare `infra.yaml` (redis) de `compose.yaml` (web).
- **Override prod** (`read_only`, `cap_drop`+`cap_add`, secrets) — avec ses **2 pièges**.
- **Secrets en 3 niveaux** : Compose `secrets:` → Ansible Vault → HashiCorp Vault.

➡️ **04-server-compose** : organiser plusieurs projets sur un serveur (edge/Traefik + projets).
