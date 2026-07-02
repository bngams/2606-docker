# 05 — Docker Swarm : d'un hôte unique à un **cluster**

> **Format.** Guide pas-à-pas. On passe de « Docker sur **une** machine » à un **cluster** de
> plusieurs nœuds, orchestré par **Swarm** (intégré à Docker, rien à installer). On simule
> plusieurs nœuds **sur un seul poste** grâce à des workers *Docker-in-Docker*.

## ✨ Objectifs

- Comprendre **manager / worker**, **service**, **tâche (task)**, **réplicas**.
- **Créer un cluster** Swarm (1 manager + 2 workers) sur une seule machine.
- Lancer des **services** répartis, les **scaler**, observer le **routing mesh**.
- Déployer une **stack** (notre app Flask + Redis) avec `docker stack deploy`.
- Faire un **rolling update** puis un **rollback**.

## 🧠 Les concepts (30 secondes)

| Terme | C'est quoi |
|---|---|
| **Nœud (node)** | une machine du cluster : **manager** (pilote) ou **worker** (exécute) |
| **Service** | la définition « je veux N conteneurs de cette image » (≈ un `deploy` déclaratif) |
| **Tâche (task)** | **une** instance (un conteneur) d'un service, placée sur un nœud |
| **Réplicas** | le **nombre** de tâches voulues pour un service (`--replicas 3`) |
| **Routing mesh** | Swarm publie un port sur **tous** les nœuds et **répartit** vers les tâches |
| **Stack** | un ensemble de services décrit dans un `compose.yml`, déployé d'un coup |

> **Compose vs Swarm :** même format de fichier, mais Swarm **orchestre sur plusieurs nœuds** et
> lit la section **`deploy:`** (réplicas, rolling update…) que `docker compose up` **ignore**.

---

## 🏗️ Étape 1 — Créer le cluster (1 manager)

Votre machine devient le **manager** (le premier nœud) :

```bash
docker swarm init
# -> affiche une commande `docker swarm join --token SWMTKN-… <IP>:2377` à garder pour les workers
```

🚧 **Récupérez** le token et l'IP du manager (utile juste après) :

```bash
SWARM_TOKEN=$(docker swarm join-token -q worker)               # le token worker
SWARM_MASTER_IP=$(docker info --format '{{.Swarm.NodeAddr}}')  # l'IP du manager
echo "$SWARM_MASTER_IP  /  $SWARM_TOKEN"
```

> 💡 **Vérifier :** `docker node ls` → une ligne, votre nœud, `MANAGER STATUS = Leader`.

---

## 🧩 Étape 2 — Ajouter des workers (simulés sur le même poste)

On n'a qu'une machine, alors on **simule** des workers avec des conteneurs **Docker-in-Docker**
(`docker:dind`) : chacun a son **propre daemon** Docker et rejoint le cluster comme un vrai nœud.

```bash
# lancer 2 workers (chacun un daemon Docker isolé et privilégié)
docker run -d --privileged --name worker-1 --hostname worker-1 docker:dind
docker run -d --privileged --name worker-2 --hostname worker-2 docker:dind
```

🚧 **Faites-les rejoindre** le manager. `docker exec` lance la commande *dans* le worker :

```bash
docker exec worker-1 docker swarm join --token "$SWARM_TOKEN" "$SWARM_MASTER_IP:2377"
docker exec worker-2 docker swarm join --token "$SWARM_TOKEN" "$SWARM_MASTER_IP:2377"
```

> 💡 **Vérifier :** `docker node ls` → **3** nœuds (1 Leader + 2 workers `Ready`).
>
> ⚠️ Les workers DinD doivent joindre le manager par une IP **routable depuis le conteneur**. Si
> `join` échoue (`timeout`), vérifiez que `worker-1` voit le manager :
> `docker exec worker-1 ping -c1 $SWARM_MASTER_IP`. Sur Docker Desktop, `$SWARM_MASTER_IP` est
> souvent l'IP de l'hôte dans le réseau bridge par défaut.

---

## 🚀 Étape 3 — Premier service & mise à l'échelle

Un **service** = « je veux N conteneurs de cette image » ; Swarm les place sur les nœuds.

```bash
# 1) créer un service web (nginx), 1 réplica, port publié 8080
docker service create --replicas 1 --name web -p 8080:80 nginx:alpine

# 2) observer
docker service ls                 # état global (REPLICAS 1/1)
docker service ps web             # les TÂCHES et sur quel nœud elles tournent
```

🚧 **Scaler** à la main et regarder Swarm répartir les tâches :

```bash
docker service scale web=3        # passe à 3 réplicas
docker service ps web             # 3 tâches, potentiellement sur des nœuds différents
```

> 💡 **Le routing mesh :** le port `8080` est publié sur **tous** les nœuds. Peu importe le nœud
> contacté, Swarm **route** vers une tâche saine. `curl http://localhost:8080` fonctionne même si
> aucune tâche `web` ne tourne « localement ».
>
> 🧪 **Tuer une tâche** pour voir l'auto-réparation : `docker rm -f <un-conteneur-web>` →
> Swarm en **recrée** une pour tenir les 3 réplicas (`docker service ps web`).

Nettoyer ce service avant la suite : `docker service rm web`.

---

## 📦 Étape 4 — Déployer une **stack** (l'app Flask + Redis)

On passe d'un service isolé à une **application complète** décrite dans un fichier. Le dossier
contient déjà l'app :

```
05-swarm/
├── app.py            # Flask : incrémente un compteur dans Redis
├── requirements.txt  # flask, redis
├── Dockerfile        # python:3.12-alpine
├── compose.yml       # UN SEUL fichier : build: (dev) + deploy: (swarm)
└── .env.example      # WEB_IMAGE = l'image poussée à déployer
```

> **Un seul fichier pour les deux mondes.** Avec la **spec Compose unifiée**, `build:` et `deploy:`
> **cohabitent** dans le même `compose.yml`. Selon l'outil qui le lit :
> - `docker compose up` (dev) → utilise **`build:`**, ignore `deploy.replicas` ;
> - `docker stack deploy` (swarm) → utilise **`deploy:`**, **ignore `build:`** (message
>   `Ignoring unsupported options: build` — c'est **normal**).

**Important — Swarm ne *build* pas** : chaque nœud doit **pull** une image déjà construite. On
**build puis on pousse** l'image sur un registre ; `compose.yml` la référence via `${WEB_IMAGE}`.

🚧 **À faire** — définir l'image, build + push (mettez **votre** compte Docker Hub / registre) :

```bash
cp .env.example .env             # puis éditez WEB_IMAGE=votre-user/stackdemo:1.0
export $(grep -v '^#' .env | xargs)   # charge WEB_IMAGE dans le shell

docker build -t "$WEB_IMAGE" .
docker login
docker push "$WEB_IMAGE"
```

Puis **déployer la stack** (Swarm lit la section `deploy:` du **même** `compose.yml`) :

```bash
docker stack deploy -c compose.yml demo
docker stack services demo        # web 3/3, redis 1/1
docker stack ps demo              # les tâches et leurs nœuds
```

> 💡 **Tester :** `curl http://localhost:8000` → *« Hello World! I have been seen N times. »*
> Rechargez : le compteur **monte** (l'état vit dans Redis, partagé par les 3 réplicas web).

> 💡 **Le même fichier en dev :** `docker compose up --build` build l'image et lance l'app sur un
> seul hôte (les `deploy.replicas` sont alors ignorés). Un fichier, deux usages.

---

## 🔄 Étape 5 — Rolling update & rollback

On met à jour l'image **sans coupure** : Swarm remplace les tâches **une par une**.

```bash
# construire/pousser une nouvelle version (VOTRE_USER/stackdemo:1.1), puis :
docker service update --image VOTRE_USER/stackdemo:1.1 demo_web
docker service ps demo_web        # anciennes tâches "Shutdown" \_ , nouvelles "Running"
```

> 💡 Le rythme est piloté par `update_config` dans `compose.yml` :
> `parallelism: 1` (une tâche à la fois), `delay: 5s`, `order: start-first` (démarre la nouvelle
> **avant** d'arrêter l'ancienne → zéro coupure).

🚧 **Rollback** si la nouvelle version pose problème — Swarm **revient** à la version précédente :

```bash
docker service rollback demo_web
docker service ps demo_web        # retour à l'image d'avant
```

---

## 🧹 Étape 6 — Nettoyage

```bash
docker stack rm demo                       # retire la stack
docker service rm web 2>/dev/null || true  # au cas où
docker rm -f worker-1 worker-2             # retirer les workers DinD
docker swarm leave --force                 # le manager quitte le swarm (dissout le cluster)
docker node ls 2>/dev/null || echo "plus de swarm — OK"
```

> 🧯 **Nœuds fantômes ?** Si `docker node ls` montre des workers en `Down` d'une session
> précédente : `docker node rm <id> --force`.

---

## 🎉 Challenge final

- [ ] Cluster **1 manager + 2 workers** (`docker node ls` → 3 nœuds).
- [ ] Service `web` **scalé à 3**, tâches réparties (`docker service ps`).
- [ ] **Auto-réparation** observée (tuer une tâche → recréée).
- [ ] **Stack** `demo` déployée (web 3/3 + redis 1/1), compteur qui monte.
- [ ] **Rolling update** puis **rollback** réussis.

## ✅ Bonus

- **`docker service logs demo_web`** pour agréger les logs des 3 réplicas.
- **Contraintes de placement** (`node.role == manager`, `node.labels…`) — déjà utilisé pour redis.
- **Secrets/Configs Swarm** : `docker secret create` (équivalent Swarm des secrets Compose du 03).
- **Portainer** en mode Swarm pour visualiser nœuds/services graphiquement.
- Un **vrai** cluster multi-machines : mêmes commandes, juste des IP réelles (VMs / cloud).

---

## 🌉 Annexe — Swarm, Compose… et Kubernetes

Swarm et Kubernetes répondent au même besoin (orchestrer des conteneurs), avec des philosophies
différentes. On peut d'ailleurs **convertir** un `compose.yml` en **manifests Kubernetes** :

| Outil | Ce qu'il fait |
|---|---|
| **`kompose convert`** | traduit un `compose.yml` en fichiers K8s (`Deployment`, `Service`…) |
| **`docker compose bridge`** | plugin Docker qui **génère** des manifests K8s (+ Kustomize) depuis un compose |

Le dossier [`out/`](out/) contient un exemple de sortie (base + overlay Kustomize) générée depuis
notre `compose.yml` — à explorer si vous enchaînez sur un module Kubernetes.

```bash
# exemple (kompose) :
kompose convert -f compose.yml -o out-kompose/

# exemple (docker compose bridge) :
docker compose bridge convert -f compose.yml --output out/
```

> ⚠️ Ces sorties sont un **point de départ** (à adapter : Ingress, ressources, probes/liveness…),
> pas un déploiement K8s prêt pour la prod.
