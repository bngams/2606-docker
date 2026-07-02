# Conteneuriser vos Applications avec les Bonnes Pratiques Docker

## Introduction

Ce tutoriel s'adresse aux professionnels IT souhaitant maîtriser la conteneurisation d'applications avec Docker. Nous aborderons les concepts fondamentaux jusqu'aux pratiques avancées de sécurité, en construisant progressivement des images optimisées et sécurisées.

**Objectifs pédagogiques :**

- Comprendre la différence entre `FROM scratch` et les images de base classiques
- Maîtriser les builds multi-étapes (multi-stage builds)
- Connaître les options essentielles de la commande `docker build`
- Appliquer les bonnes pratiques de sécurité (utilisateur non-root, capabilities, health checks, limites de ressources)
- Savoir observer et auditer un conteneur en cours d'exécution

---

## 1. Images de Base : FROM scratch vs Images Classiques

### 1.1 Qu'est-ce qu'une Image de Base ?

Une image de base (base image) constitue le point de départ de votre Dockerfile. Elle fournit le système de fichiers initial sur lequel vous allez construire votre application.

**Images classiques courantes :**

| Image | Taille approximative | Cas d'usage |
|-------|---------------------|-------------|
| `ubuntu:24.04` | ~77 MB | Applications nécessitant un environnement complet |
| `debian:bookworm-slim` | ~74 MB | Compromis entre fonctionnalités et taille |
| `alpine:3.19` | ~7 MB | Images légères, utilise musl libc |
| `scratch` | 0 octets | Image vide, contrôle total |

### 1.2 L'Image scratch : Le Point Zéro

L'image `scratch` est une image spéciale réservée par Docker. Elle est littéralement **vide** : aucun fichier, aucun dossier, aucun shell, aucune bibliothèque.

```dockerfile
# Cette référence indique à Docker de partir d'une image vide
FROM scratch
```

**Caractéristiques importantes de scratch :**

- Impossible de la télécharger avec `docker pull scratch`
- Impossible de l'exécuter directement avec `docker run scratch`
- Utilisable uniquement comme référence dans un Dockerfile
- Produit les images les plus petites possibles

### 1.3 Quand Utiliser scratch ?

**Avantages :**

- **Taille minimale** : L'image finale ne contient que votre application
- **Surface d'attaque réduite** : Aucun outil système pouvant être exploité
- **Contrôle total** : Vous savez exactement ce qui est présent
- **Conformité** : Idéal pour les environnements réglementés
- **Déploiement edge** : Mises à jour rapides sur connexions limitées

**Inconvénients :**

- **Débogage difficile** : Pas de shell, pas de `curl`, pas de `ping`
- **Binaire autonome requis** : L'exécutable doit être compilé statiquement
- **Connaissance approfondie nécessaire** : Comprendre le processus de build

### 1.4 Exemple Comparatif

**Image avec Alpine (230 MB) :**

```dockerfile
FROM golang:1.21.6-alpine3.18 AS build
WORKDIR /go/src/app
COPY ./src/* .
RUN go mod download
RUN GOOS=linux go build -o /go/bin/app -v .

FROM golang:1.21.6-alpine3.18
COPY --from=build /go/bin/app /go/bin/app
EXPOSE 8080
ENTRYPOINT [ "/go/bin/app" ]
```

**Image avec scratch (6.82 MB) :**

```dockerfile
FROM golang:1.21.6-alpine3.18 AS build
WORKDIR /go/src/app
COPY ./src/* .
RUN go mod download
RUN GOOS=linux go build -ldflags="-s" -o /go/bin/app -v .

FROM scratch
COPY --from=build /go/bin/app /go/bin/app
EXPOSE 8080
ENTRYPOINT [ "/go/bin/app" ]
```

> **Note :** Le flag `-ldflags="-s"` supprime les informations de débogage du binaire, réduisant sa taille. C'est une pratique courante pour les builds de production.

---

## 2. Les Builds Multi-Étapes (Multi-Stage Builds)

### 2.1 Concept et Motivation

Un build multi-étapes permet d'utiliser **plusieurs instructions `FROM`** dans un même Dockerfile. Chaque `FROM` démarre une nouvelle étape avec sa propre image de base.

**Problème résolu :** Dans un build traditionnel, toutes les dépendances de compilation (compilateurs, outils de build, bibliothèques de développement) se retrouvent dans l'image finale, augmentant sa taille et sa surface d'attaque.

**Solution :** Séparer l'environnement de build de l'environnement d'exécution.

### 2.2 Anatomie d'un Build Multi-Étapes

```dockerfile
# ============================================
# ÉTAPE 1 : Build (environnement de compilation)
# ============================================
FROM golang:1.21.6-alpine3.18 AS build

# Installer les dépendances de build si nécessaire
RUN apk add --no-cache git

WORKDIR /go/src/app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app/server .

# ============================================
# ÉTAPE 2 : Runtime (environnement d'exécution)
# ============================================
FROM scratch

# Copier uniquement le binaire compilé
COPY --from=build /app/server /server

EXPOSE 8080
ENTRYPOINT ["/server"]
```

**Éléments clés :**

- `AS build` : Nomme l'étape pour pouvoir y faire référence
- `COPY --from=build` : Copie des fichiers depuis une étape précédente
- L'image finale ne contient que ce qui est explicitement copié

### 2.3 Patterns Avancés

**Pattern : Étape de base partagée**

```dockerfile
# Étape commune pour fixer la version
FROM alpine:3.19 AS alpine

# Étape de build
FROM alpine AS builder
RUN apk add --no-cache build-base
COPY . /src
RUN make -C /src

# Étape de test
FROM alpine AS tester
COPY --from=builder /src/app /app
RUN /app --self-test

# Étape finale
FROM alpine
COPY --from=builder /src/app /usr/local/bin/app
CMD ["app"]
```

**Pattern : Copie depuis une image externe**

```dockerfile
FROM scratch

# Copier depuis une image externe (pas une étape du build)
COPY --from=nginx:alpine /etc/nginx/nginx.conf /nginx.conf
COPY --from=build /app /app

CMD ["/app"]
```

### 2.4 Avantages des Builds Multi-Étapes

| Aspect | Bénéfice |
|--------|----------|
| **Taille d'image** | Réduction drastique (souvent 90%+) |
| **Sécurité** | Pas d'outils de build en production |
| **Maintenabilité** | Un seul Dockerfile à gérer |
| **Cache** | BuildKit optimise et parallélise les étapes |
| **Reproductibilité** | Build complet dans un environnement contrôlé |

---

## 3. Options de la Commande docker build

### 3.1 Syntaxe Générale

```bash
docker build [OPTIONS] PATH | URL | -
```

Le `PATH` correspond au **contexte de build** : le répertoire dont le contenu sera envoyé au daemon Docker.

### 3.2 Options Essentielles

#### Tag de l'image (-t, --tag)

Attribue un nom et optionnellement un tag à l'image construite.

```bash
# Format : nom:tag
docker build -t mon-app:1.0.0 .
docker build -t mon-registry.io/mon-app:latest .

# Tags multiples
docker build -t mon-app:1.0.0 -t mon-app:latest .
```

#### Fichier Dockerfile (-f, --file)

Spécifie un Dockerfile alternatif (par défaut : `./Dockerfile`).

```bash
docker build -f Dockerfile.production -t mon-app:prod .
docker build -f dockerfiles/Dockerfile.dev -t mon-app:dev .
```

#### Sans cache (--no-cache)

Force la reconstruction de toutes les couches, ignorant le cache.

```bash
# Utile pour garantir un build propre ou comparer les temps de build
docker build --no-cache -t mon-app:1.0.0 .
```

#### Étape cible (--target)

Construit uniquement jusqu'à une étape spécifique (utile avec les multi-stage builds).

```bash
# Construire uniquement l'étape de build pour déboguer
docker build --target build -t mon-app:debug .

# Construire l'étape de test
docker build --target tester -t mon-app:test .
```

#### Arguments de build (--build-arg)

Passe des variables au build, utilisables avec l'instruction `ARG`.

```dockerfile
ARG GO_VERSION=1.21
FROM golang:${GO_VERSION}-alpine AS build
```

```bash
docker build --build-arg GO_VERSION=1.22 -t mon-app:1.0.0 .
```

#### Plateforme cible (--platform)

Construit pour une architecture spécifique (builds cross-platform).

```bash
# Build pour ARM64 (ex: Raspberry Pi, Apple Silicon)
docker build --platform linux/arm64 -t mon-app:arm64 .

# Build pour AMD64
docker build --platform linux/amd64 -t mon-app:amd64 .
```

### 3.3 Options de Performance et Cache

#### Cache externe (--cache-from, --cache-to)

Utilise une image comme source de cache ou exporte le cache.

```bash
# Utiliser une image comme cache
docker build --cache-from mon-app:latest -t mon-app:1.0.0 .

# Export du cache (avec BuildKit)
docker build --cache-to type=inline -t mon-app:1.0.0 .
```

#### Sortie personnalisée (--output, -o)

Exporte le résultat du build vers un répertoire local au lieu de créer une image.

```bash
# Exporter les fichiers de l'image vers un dossier local
docker build --output type=local,dest=./output .

# Exporter uniquement le binaire
docker build --target build --output type=local,dest=./bin .
```

### 3.4 Options de Sécurité

#### Secrets de build (--secret)

Passe des secrets au build sans les inclure dans l'image finale.

```bash
docker build --secret id=mysecret,src=./secret.txt -t mon-app:1.0.0 .
```

```dockerfile
# Dans le Dockerfile
RUN --mount=type=secret,id=mysecret cat /run/secrets/mysecret
```

#### SSH (--ssh)

Permet l'accès SSH pendant le build (ex: cloner des repos privés).

```bash
docker build --ssh default -t mon-app:1.0.0 .
```

### 3.5 Tableau Récapitulatif

| Option | Description | Exemple |
|--------|-------------|---------|
| `-t, --tag` | Nom et tag de l'image | `-t app:1.0` |
| `-f, --file` | Chemin du Dockerfile | `-f Dockerfile.prod` |
| `--no-cache` | Ignorer le cache | `--no-cache` |
| `--target` | Étape cible | `--target build` |
| `--build-arg` | Variable de build | `--build-arg VERSION=1.0` |
| `--platform` | Architecture cible | `--platform linux/arm64` |
| `--cache-from` | Source de cache | `--cache-from app:latest` |
| `--output` | Export local | `-o type=local,dest=./out` |
| `--secret` | Secret de build | `--secret id=key,src=./key` |
| `--progress` | Format de sortie | `--progress=plain` |

---

## 4. Sécurité des Conteneurs

### 4.1 Utilisateur Non-Root (UID/GID)

#### Pourquoi c'est Important

Par défaut, les processus dans un conteneur s'exécutent en tant que **root** (UID 0). Cela pose plusieurs risques :

- **Escalade de privilèges** : Si un attaquant compromet le conteneur, il a les droits root
- **Accès aux fichiers de l'hôte** : Via les volumes montés, root dans le conteneur = root sur les fichiers
- **Exploitation de vulnérabilités** : Les CVE sont souvent plus graves avec des droits root

#### Créer un Utilisateur Non-Root

**Méthode 1 : Avec adduser (recommandée pour images avec shell)**

```dockerfile
FROM golang:1.21.6-alpine3.18 AS build
# Créer l'utilisateur dans l'étape de build
RUN adduser --disabled-password --gecos "" --uid 10001 appuser

WORKDIR /go/src/app
COPY . .
RUN go build -o /app/server .

FROM scratch
# Copier le fichier passwd
COPY --from=build /etc/passwd /etc/passwd
COPY --from=build /app/server /server

# Définir l'utilisateur
USER appuser

EXPOSE 8080
ENTRYPOINT ["/server"]
```

**Méthode 2 : Créer un /etc/passwd minimal (pour scratch)**

```dockerfile
FROM golang:1.21.6-alpine3.18 AS build
WORKDIR /go/src/app
COPY . .
RUN go build -ldflags="-s" -o /app/server .

# Créer un fichier passwd minimaliste
RUN echo "appuser:x:10001:10001:App User:/:/sbin/nologin" > /etc/minimal-passwd

FROM scratch
COPY --from=build /app/server /server
COPY --from=build /etc/minimal-passwd /etc/passwd

USER appuser
EXPOSE 8080
ENTRYPOINT ["/server"]
```

#### Bonnes Pratiques UID/GID

| Pratique | Raison |
|----------|--------|
| UID > 10000 | Évite les conflits avec les utilisateurs système de l'hôte |
| UID fixe et documenté | Permet de gérer les permissions sur les volumes |
| Pas de shell (`/sbin/nologin`) | Réduit la surface d'attaque |
| GID identique à l'UID | Simplifie la gestion des permissions |

#### Vérifier l'Utilisateur d'un Conteneur

```bash
# Voir le processus et son UID
docker container top <nom_ou_id>

# Exemple de sortie avec root :
# UID    PID    PPID   CMD
# root   8145   8119   /go/bin/app

# Exemple de sortie avec utilisateur non-root :
# UID    PID    PPID   CMD
# 10001  10868  10843  /go/bin/app

# Inspecter la configuration utilisateur
docker inspect <nom_ou_id> --format '{{.Config.User}}'

# Vérifier depuis l'intérieur du conteneur (si shell disponible)
docker exec <nom_ou_id> id
docker exec <nom_ou_id> whoami
```

---

### 4.2 Health Checks (Vérifications de Santé)

#### Concept

Un health check permet à Docker de vérifier si l'application dans le conteneur fonctionne correctement, au-delà du simple fait que le processus tourne.

**États possibles :**

- `starting` : Le conteneur démarre, les health checks n'ont pas encore eu lieu
- `healthy` : Le dernier health check a réussi
- `unhealthy` : Plusieurs health checks consécutifs ont échoué

#### Syntaxe dans le Dockerfile

```dockerfile
HEALTHCHECK [OPTIONS] CMD <commande>
```

**Options disponibles :**

| Option | Défaut | Description |
|--------|--------|-------------|
| `--interval` | 30s | Intervalle entre les vérifications |
| `--timeout` | 30s | Temps max pour qu'une vérification réponde |
| `--start-period` | 0s | Délai avant la première vérification |
| `--retries` | 3 | Nombre d'échecs avant de passer en "unhealthy" |

**Codes de retour :**

- `0` : Succès (healthy)
- `1` : Échec (unhealthy)
- `2` : Réservé (ne pas utiliser)

#### Exemples Pratiques

**Application Web avec curl :**

```dockerfile
FROM node:20-alpine

WORKDIR /app
COPY . .
RUN npm install

# Health check : vérifie que le serveur répond
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

EXPOSE 3000
CMD ["npm", "start"]
```

**Application Web avec wget (si curl n'est pas disponible) :**

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8080/health || exit 1
```

**Image scratch avec binaire intégré :**

Pour les images scratch, vous devez intégrer la logique de health check dans votre application ou copier un binaire dédié.

```dockerfile
FROM golang:1.21-alpine AS build
WORKDIR /app
COPY . .
RUN go build -o /server .
RUN go build -o /healthcheck ./cmd/healthcheck

FROM scratch
COPY --from=build /server /server
COPY --from=build /healthcheck /healthcheck

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["/healthcheck"]

ENTRYPOINT ["/server"]
```

#### Dans Docker Compose

```yaml
services:
  api:
    build: .
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

#### Commandes d'Observation

```bash
# Voir l'état de santé dans la liste des conteneurs
docker ps
# CONTAINER ID   IMAGE     STATUS
# abc123         app:1.0   Up 5 min (healthy)

# Détails du health check
docker inspect <nom_ou_id> --format '{{json .State.Health}}' | jq

# Historique des health checks
docker inspect <nom_ou_id> --format '{{range .State.Health.Log}}{{.End}} - {{.ExitCode}}{{println}}{{end}}'
```

---

### 4.3 Linux Capabilities

#### Concept

Les capabilities Linux divisent les privilèges traditionnellement associés au superutilisateur (root) en unités distinctes. Cela permet un contrôle fin des permissions.

**Exemples de capabilities :**

| Capability | Description |
|------------|-------------|
| `CAP_CHOWN` | Modifier l'UID/GID des fichiers |
| `CAP_NET_BIND_SERVICE` | Lier un socket aux ports < 1024 |
| `CAP_NET_RAW` | Utiliser les sockets RAW (ping, etc.) |
| `CAP_SYS_TIME` | Modifier l'heure système |
| `CAP_SETUID` | Changer d'UID |
| `CAP_DAC_OVERRIDE` | Ignorer les permissions de fichiers |

#### Capabilities par Défaut de Docker

Docker accorde par défaut un ensemble limité de capabilities :

```
CHOWN, DAC_OVERRIDE, FSETID, FOWNER, MKNOD, NET_RAW, 
SETGID, SETUID, SETFCAP, SETPCAP, NET_BIND_SERVICE, 
SYS_CHROOT, KILL, AUDIT_WRITE
```

#### Principe du Moindre Privilège

La meilleure pratique est de **supprimer toutes les capabilities** puis d'ajouter uniquement celles nécessaires.

```bash
# Supprimer toutes les capabilities
docker run --cap-drop=ALL mon-image

# Supprimer toutes puis ajouter uniquement ce qui est nécessaire
docker run --cap-drop=ALL --cap-add=NET_BIND_SERVICE mon-image

# Supprimer une capability spécifique
docker run --cap-drop=NET_RAW mon-image

# Ajouter une capability (ex: pour modifier l'heure)
docker run --cap-add=SYS_TIME ntpd
```

> **⚠️ IMPORTANT** : Ne jamais utiliser `--privileged` en production ! Ce flag accorde TOUTES les capabilities au conteneur.

#### Dans Docker Compose

```yaml
services:
  app:
    image: mon-app:1.0
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
```

#### Capabilities Couramment Supprimables

Pour la plupart des applications web, vous pouvez supprimer :

```bash
docker run --cap-drop=ALL \
    --cap-add=CHOWN \
    --cap-add=SETGID \
    --cap-add=SETUID \
    mon-app
```

Ou de manière plus agressive pour une application qui ne fait rien de spécial :

```bash
docker run --cap-drop=ALL mon-app
```

#### Vérifier les Capabilities d'un Conteneur

**Depuis l'hôte :**

```bash
# Installer l'outil pscap (paquet libcap-ng-utils)
sudo apt install libcap-ng-utils

# Lister les capabilities des processus
pscap

# Exemple de sortie :
# PID   PPID  UID   COMMAND     CAPABILITIES
# 12345 12300 0     nginx       chown, dac_override, ...

# Vérifier les capabilities d'un processus spécifique
cat /proc/<PID>/status | grep Cap

# Décoder les valeurs hexadécimales
capsh --decode=<valeur_hex>
```

**Depuis l'intérieur du conteneur :**

```bash
# Si capsh est disponible
docker exec <conteneur> capsh --print

# Exemple de sortie :
# Current: cap_chown,cap_dac_override,cap_fowner,...=ep
# Bounding set: cap_chown,cap_dac_override,...

# Avec getpcaps
docker exec <conteneur> getpcaps $$
```

**Avec Docker inspect :**

```bash
# Voir la configuration des capabilities
docker inspect <conteneur> --format '{{.HostConfig.CapAdd}}'
docker inspect <conteneur> --format '{{.HostConfig.CapDrop}}'
```

---

### 4.4 Limites de Ressources (CPU et Mémoire)

#### Concept : cgroups

Docker utilise les **cgroups** (control groups) du noyau Linux pour limiter les ressources qu'un conteneur peut consommer. Sans limites, un conteneur peut monopoliser toutes les ressources de l'hôte.

#### Limites Mémoire

```bash
# Limite dure : le conteneur ne peut pas dépasser cette valeur
docker run -m 512m mon-app
docker run --memory=512m mon-app

# Limite souple (reservation) : garantie minimum si ressources disponibles
docker run -m 512m --memory-reservation=256m mon-app

# Limite avec swap
docker run -m 512m --memory-swap=1g mon-app

# Désactiver le swap pour le conteneur
docker run -m 512m --memory-swap=512m mon-app
```

**Comportement :**

- Si le conteneur dépasse la limite mémoire, le kernel Linux déclenche un **OOM (Out Of Memory)** et tue le processus
- La limite souple est utilisée quand l'hôte manque de mémoire

#### Limites CPU

```bash
# Limiter à 0.5 CPU (50% d'un cœur)
docker run --cpus=0.5 mon-app

# Limiter à 2 CPUs
docker run --cpus=2 mon-app

# Limiter à des cœurs spécifiques (0 et 1)
docker run --cpuset-cpus="0,1" mon-app

# Priorité relative (par défaut 1024, plus = priorité plus haute)
docker run --cpu-shares=512 mon-app

# Configuration avancée avec period/quota
# Limite à 50% d'un CPU (50ms sur période de 100ms)
docker run --cpu-period=100000 --cpu-quota=50000 mon-app
```

**Différence entre les options CPU :**

| Option | Type | Description |
|--------|------|-------------|
| `--cpus` | Limite dure | Nombre max de CPUs utilisables |
| `--cpu-shares` | Limite relative | Poids en cas de contention |
| `--cpuset-cpus` | Affectation | Quels cœurs sont utilisables |
| `--cpu-period/quota` | Limite dure | Contrôle fin du temps CPU |

#### Dans Docker Compose

```yaml
services:
  app:
    image: mon-app:1.0
    deploy:
      resources:
        limits:
          cpus: '0.50'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 128M
```

**Syntaxe ancienne (docker-compose v2) :**

```yaml
services:
  app:
    image: mon-app:1.0
    mem_limit: 512m
    mem_reservation: 128m
    cpus: 0.5
```

#### Commandes d'Observation

**Statistiques en temps réel :**

```bash
# Stats de tous les conteneurs
docker stats

# CONTAINER ID   NAME     CPU %   MEM USAGE / LIMIT   MEM %   NET I/O   BLOCK I/O   PIDS
# abc123         app      0.50%   128MiB / 512MiB     25.00%  1.2kB/0B  0B/0B       5

# Stats d'un conteneur spécifique
docker stats mon-app

# Sans flux continu (snapshot)
docker stats --no-stream
```

**Vérifier les limites configurées :**

```bash
# Inspecter les limites mémoire
docker inspect <conteneur> --format '{{.HostConfig.Memory}}'

# Inspecter les limites CPU
docker inspect <conteneur> --format '{{.HostConfig.NanoCpus}}'
# Note : 1 CPU = 1000000000 nanoCPUs

# Toutes les limites de ressources
docker inspect <conteneur> --format '{{json .HostConfig}}' | jq '{
  Memory: .Memory,
  MemoryReservation: .MemoryReservation,
  MemorySwap: .MemorySwap,
  NanoCpus: .NanoCpus,
  CpuShares: .CpuShares,
  CpusetCpus: .CpusetCpus
}'
```

**Accès direct aux cgroups (sur l'hôte Linux) :**

```bash
# Obtenir l'ID complet du conteneur
CONTAINER_ID=$(docker inspect <conteneur> --format '{{.Id}}')

# cgroups v1
cat /sys/fs/cgroup/memory/docker/${CONTAINER_ID}/memory.limit_in_bytes
cat /sys/fs/cgroup/cpu/docker/${CONTAINER_ID}/cpu.cfs_quota_us
cat /sys/fs/cgroup/cpu/docker/${CONTAINER_ID}/cpu.cfs_period_us

# cgroups v2 (systèmes récents)
cat /sys/fs/cgroup/system.slice/docker-${CONTAINER_ID}.scope/memory.max
cat /sys/fs/cgroup/system.slice/docker-${CONTAINER_ID}.scope/cpu.max
```

---

## 5. Dockerfile Complet Sécurisé : Exemple de Référence

Voici un Dockerfile complet intégrant toutes les bonnes pratiques abordées :

```dockerfile
# ============================================
# Dockerfile de Production Sécurisé
# Application Go avec toutes les bonnes pratiques
# ============================================

# Arguments de build avec valeurs par défaut
ARG GO_VERSION=1.21
ARG ALPINE_VERSION=3.19

# ============================================
# ÉTAPE 1 : Build
# ============================================
FROM golang:${GO_VERSION}-alpine${ALPINE_VERSION} AS build

# Métadonnées
LABEL stage=build

# Installer les dépendances de build si nécessaire
RUN apk add --no-cache git ca-certificates tzdata

WORKDIR /src

# Copier les fichiers de dépendances d'abord (meilleur cache)
COPY go.mod go.sum ./
RUN go mod download && go mod verify

# Copier le code source
COPY . .

# Build statique avec optimisations
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-s -w -extldflags '-static'" \
    -o /app/server \
    ./cmd/server

# Créer le fichier passwd minimal pour l'utilisateur non-root
RUN echo "appuser:x:10001:10001:App User:/nonexistent:/sbin/nologin" > /etc/app-passwd

# ============================================
# ÉTAPE 2 : Image Finale
# ============================================
FROM scratch

# Métadonnées de l'image
LABEL maintainer="equipe@example.com"
LABEL version="1.0.0"
LABEL description="Application API sécurisée"

# Copier les certificats CA (nécessaire pour HTTPS)
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/

# Copier les données de timezone (si nécessaire)
COPY --from=build /usr/share/zoneinfo /usr/share/zoneinfo

# Copier le fichier passwd pour l'utilisateur non-root
COPY --from=build /etc/app-passwd /etc/passwd

# Copier le binaire
COPY --from=build /app/server /server

# Définir l'utilisateur non-root
USER appuser

# Exposer le port (documentation)
EXPOSE 8080

# Health check intégré (nécessite un binaire de healthcheck ou endpoint HTTP)
# Note : Pour scratch, vous devez avoir un endpoint /health dans votre app
# HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
#     CMD ["/healthcheck"]

# Point d'entrée
ENTRYPOINT ["/server"]
```

**Commande de build et d'exécution sécurisée :**

```bash
# Build
docker build \
    --no-cache \
    --build-arg GO_VERSION=1.22 \
    -t mon-app:1.0.0-secure \
    -f Dockerfile.secure \
    .

# Exécution sécurisée
docker run -d \
    --name mon-app \
    --cap-drop=ALL \
    --read-only \
    --memory=256m \
    --cpus=0.5 \
    -p 8080:8080 \
    mon-app:1.0.0-secure
```

---

## 6. Commandes d'Audit et d'Observation

### 6.1 Récapitulatif des Commandes d'Observation

| Aspect | Commande |
|--------|----------|
| **Utilisateur** | `docker container top <id>` |
| **Utilisateur (config)** | `docker inspect <id> --format '{{.Config.User}}'` |
| **Health status** | `docker inspect <id> --format '{{json .State.Health}}'` |
| **Capabilities ajoutées** | `docker inspect <id> --format '{{.HostConfig.CapAdd}}'` |
| **Capabilities supprimées** | `docker inspect <id> --format '{{.HostConfig.CapDrop}}'` |
| **Limites mémoire** | `docker inspect <id> --format '{{.HostConfig.Memory}}'` |
| **Limites CPU** | `docker inspect <id> --format '{{.HostConfig.NanoCpus}}'` |
| **Stats temps réel** | `docker stats <id>` |
| **Logs** | `docker logs <id>` |

### 6.2 Script d'Audit Rapide

```bash
#!/bin/bash
# audit-container.sh - Audit de sécurité d'un conteneur

CONTAINER=$1

if [ -z "$CONTAINER" ]; then
    echo "Usage: $0 <container_name_or_id>"
    exit 1
fi

echo "=== AUDIT DU CONTENEUR: $CONTAINER ==="
echo ""

echo "--- Utilisateur ---"
docker inspect $CONTAINER --format 'Config User: {{.Config.User}}'
docker container top $CONTAINER 2>/dev/null || echo "Conteneur non en cours d'exécution"
echo ""

echo "--- Capabilities ---"
echo "Ajoutées: $(docker inspect $CONTAINER --format '{{.HostConfig.CapAdd}}')"
echo "Supprimées: $(docker inspect $CONTAINER --format '{{.HostConfig.CapDrop}}')"
echo "Privileged: $(docker inspect $CONTAINER --format '{{.HostConfig.Privileged}}')"
echo ""

echo "--- Limites Ressources ---"
MEMORY=$(docker inspect $CONTAINER --format '{{.HostConfig.Memory}}')
NANO_CPUS=$(docker inspect $CONTAINER --format '{{.HostConfig.NanoCpus}}')
echo "Mémoire: $(($MEMORY / 1024 / 1024)) MB"
echo "CPUs: $(echo "scale=2; $NANO_CPUS / 1000000000" | bc)"
echo ""

echo "--- Health Check ---"
docker inspect $CONTAINER --format '{{json .State.Health}}' 2>/dev/null | jq . || echo "Pas de health check configuré"
echo ""

echo "--- Système de fichiers ---"
echo "Read-only: $(docker inspect $CONTAINER --format '{{.HostConfig.ReadonlyRootfs}}')"
echo ""

echo "--- Réseau ---"
docker inspect $CONTAINER --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```

---

## 7. Résumé et Checklist de Sécurité

### Checklist de Production

- [ ] **Image de base minimale** : Utiliser `scratch`, `distroless`, ou `alpine`
- [ ] **Multi-stage build** : Séparer build et runtime
- [ ] **Utilisateur non-root** : UID > 10000, pas de shell
- [ ] **Capabilities minimales** : `--cap-drop=ALL` puis ajouter le nécessaire
- [ ] **Health check** : Vérification de santé applicative
- [ ] **Limites de ressources** : Mémoire et CPU définies
- [ ] **Système de fichiers read-only** : `--read-only` si possible
- [ ] **Pas de secrets dans l'image** : Utiliser les secrets Docker ou variables d'environnement
- [ ] **Scan de vulnérabilités** : `docker scout`, Trivy, ou équivalent
- [ ] **Tags immutables** : Utiliser des versions spécifiques, pas `latest`

### Commande de Lancement Sécurisée Type

```bash
docker run -d \
    --name mon-app \
    --user 10001:10001 \
    --cap-drop=ALL \
    --cap-add=NET_BIND_SERVICE \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --memory=256m \
    --memory-swap=256m \
    --cpus=0.5 \
    --pids-limit=100 \
    --security-opt=no-new-privileges:true \
    --health-cmd='wget -q --spider http://localhost:8080/health || exit 1' \
    --health-interval=30s \
    --health-timeout=3s \
    --health-retries=3 \
    -p 8080:8080 \
    mon-app:1.0.0
```

---

## Références

- [Documentation Docker - Images de base](https://docs.docker.com/build/building/base-images/)
- [Documentation Docker - Multi-stage builds](https://docs.docker.com/build/building/multi-stage/)
- [Documentation Docker - Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Docker Security Best Practices - OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Linux Capabilities - man pages](https://man7.org/linux/man-pages/man7/capabilities.7.html)

---

*Document créé pour la formation Docker - Bonnes Pratiques de Conteneurisation*
