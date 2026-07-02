# Workshop : Créer un Conteneur avec runc

## Objectif

Dans ce workshop, vous allez créer, démarrer, et gérer un conteneur Nginx en utilisant `runc`, le runtime de conteneurs de bas niveau qui est au cœur de Docker, containerd, et Kubernetes.

Ce workshop vous apprendra à :
- Utiliser `runc` en ligne de commande
- Comprendre les spécifications OCI (Open Container Initiative)
- Configurer un conteneur manuellement via `config.json`
- Gérer le cycle de vie d'un conteneur (create, start, exec, kill, delete)
- Configurer le réseau d'un conteneur

## Ressources

Ce workshop s'inspire du challenge :
- [Create and Start a Container Manually With runc](https://labs.iximiuz.com/challenges/start-container-with-runc)

## Prérequis

- Avoir complété le workshop "Construire un Conteneur From Scratch"
- Machine Linux Debian/Ubuntu avec accès root
- Connaissances de base en JSON
- Avoir lu le document théorique sur l'architecture des conteneurs

---

## Préparation de l'Environnement

### Installation de runc

```bash
# Méthode 1 : Via apt (Debian/Ubuntu)
sudo apt update
sudo apt install -y runc

# Vérifier l'installation
runc --version
# Devrait afficher : runc version 1.x.x

# Méthode 2 : Téléchargement direct depuis GitHub (version plus récente)
RUNC_VERSION="v1.1.12"
wget https://github.com/opencontainers/runc/releases/download/${RUNC_VERSION}/runc.amd64
sudo install -m 755 runc.amd64 /usr/local/bin/runc
rm runc.amd64
```

### Installation des Outils Complémentaires

```bash
# Installer les outils pour extraire les images
sudo apt install -y \
    uidmap \
    curl \
    wget \
    ca-certificates

# Installer crane (pour extraire les images)
curl -sL "https://github.com/google/go-containerregistry/releases/download/v0.19.0/go-containerregistry_Linux_x86_64.tar.gz" | \
sudo tar -C /usr/local/bin -xzf - crane

# Vérifier
crane version
```

---

## Partie 1 : Comprendre le Workflow runc

### Architecture runc

```
┌────────────────────────────────────────────────────────┐
│                   Utilisateur                          │
│                (docker run, ctr, crictl)               │
└─────────────────────┬──────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────────────────┐
│              High-Level Runtime                        │
│         (containerd, CRI-O, Docker)                    │
└─────────────────────┬──────────────────────────────────┘
                      │ Prépare le bundle OCI
                      │ (rootfs + config.json)
                      ▼
┌────────────────────────────────────────────────────────┐
│                     runc                               │
│                                                        │
│  Commandes principales :                               │
│  • runc create  : Crée le conteneur (prépare)         │
│  • runc start   : Démarre le processus principal      │
│  • runc run     : create + start en une commande      │
│  • runc exec    : Exécute une commande dans le        │
│                   conteneur                           │
│  • runc kill    : Envoie un signal au conteneur       │
│  • runc delete  : Supprime le conteneur               │
│  • runc list    : Liste les conteneurs                │
│  • runc state   : Affiche l'état d'un conteneur       │
└─────────────────────┬──────────────────────────────────┘
                      │
                      ▼
┌────────────────────────────────────────────────────────┐
│                  Noyau Linux                           │
│         (Namespaces, Cgroups, Capabilities)            │
└────────────────────────────────────────────────────────┘
```

### Workflow Typique

```
1. Préparer un Bundle OCI
   ├── rootfs/          (système de fichiers du conteneur)
   └── config.json      (configuration OCI)

2. runc create <container-id>
   ├── Crée les namespaces
   ├── Configure les cgroups
   ├── Lance le processus "runc init" (stub)
   └── État : created (mais pas encore running)

3. runc start <container-id>
   ├── Remplace "runc init" par le processus réel
   └── État : running

4. runc exec <container-id> <command>
   └── Exécute une commande dans le conteneur running

5. runc kill <container-id> <signal>
   └── Envoie un signal (SIGTERM, SIGKILL, etc.)

6. runc delete <container-id>
   └── Nettoie les ressources (namespaces, cgroups)
```

---

## Partie 2 : Créer un Bundle OCI

### Exercice 2.1 : Créer le Répertoire Bundle

Un **bundle** est simplement un répertoire contenant :
- Un dossier `rootfs/` avec le système de fichiers du conteneur
- Un fichier `config.json` avec la configuration OCI

```bash
# Créer le répertoire bundle dans $HOME
cd ~
mkdir -p mycontainer
cd mycontainer

# Vérifier que nous sommes dans le bon répertoire
pwd
# Devrait afficher : /home/<username>/mycontainer
```

### Exercice 2.2 : Générer le Fichier config.json

```bash
# Générer un fichier config.json par défaut
runc spec

# Afficher le contenu
cat config.json | head -40
```

**Observation** : Le fichier `config.json` contient :
- `ociVersion` : Version de la spec OCI
- `process` : Configuration du processus à lancer
  - `terminal` : Allouer un TTY ou non
  - `user` : UID/GID du processus
  - `args` : Commande et arguments
  - `env` : Variables d'environnement
  - `cwd` : Répertoire de travail
- `root` : Chemin vers le rootfs
- `hostname` : Hostname du conteneur
- `mounts` : Points de montage
- `linux` : Configuration Linux spécifique
  - `namespaces` : Liste des namespaces à créer
  - `resources` : Limites de ressources (cgroups)

### Exercice 2.3 : Extraire le Rootfs de l'Image Nginx

```bash
# Créer le répertoire rootfs
mkdir -p rootfs

# Méthode 1 : Avec crane
crane export nginx:latest | tar -xC rootfs/

# Méthode 2 : Avec Docker (si installé)
# docker export $(docker create nginx:latest) | tar -xC rootfs/

# Vérifier le contenu
ls -l rootfs/
```

### Exercice 2.4 : Comprendre la Structure du Bundle

```bash
# Structure du bundle
tree -L 1 ~/mycontainer

# Devrait afficher :
# ~/mycontainer
# ├── config.json
# └── rootfs/
#     ├── bin/
#     ├── etc/
#     ├── usr/
#     ├── var/
#     └── ...
```

---

## Partie 3 : Configurer le Conteneur

### Exercice 3.1 : Analyser la Configuration par Défaut

```bash
# Afficher la commande qui sera exécutée
jq '.process.args' config.json
# Par défaut : ["sh"]
```

### Exercice 3.2 : Configurer pour Nginx

Nginx n'est pas un processus interactif - il n'a pas besoin de TTY. De plus, nous devons spécifier la bonne commande de démarrage.

```bash
# Option 1 : Vérifier la commande dans l'image Docker
docker inspect nginx:latest | jq '.[0].Config.Cmd'
# Devrait afficher : ["nginx", "-g", "daemon off;"]

# Option 2 : Modifier config.json avec jq
jq '.process.terminal = false' config.json > config.tmp && mv config.tmp config.json

jq '.process.args = ["nginx", "-g", "daemon off;"]' config.json > config.tmp && mv config.tmp config.json

# Option 3 : Éditer manuellement config.json
# nano config.json ou vim config.json
# Chercher "process" > "args" et remplacer par : ["nginx", "-g", "daemon off;"]
# Chercher "process" > "terminal" et remplacer par : false
```

### Exercice 3.3 : Vérifier la Configuration

```bash
# Vérifier les changements
jq '.process.args' config.json
# ["nginx", "-g", "daemon off;"]

jq '.process.terminal' config.json
# false
```

---

## Partie 4 : Créer et Démarrer le Conteneur

### Exercice 4.1 : Créer le Conteneur

```bash
# Se positionner dans le bundle
cd ~/mycontainer

# Créer le conteneur (ne le démarre pas encore)
sudo runc create nginx-container

# Vérifier l'état
sudo runc state nginx-container
```

**Sortie attendue** :
```json
{
  "ociVersion": "1.0.0",
  "id": "nginx-container",
  "pid": 12345,
  "status": "created",
  "bundle": "/home/<username>/mycontainer",
  "rootfs": "/home/<username>/mycontainer/rootfs",
  "created": "2024-01-15T10:30:00.123456789Z"
}
```

**Observation** :
- `status: created` : Le conteneur est créé mais pas encore démarré
- `pid` : PID du processus "runc init" (stub qui tient les namespaces)

### Exercice 4.2 : Inspecter le Processus runc init

```bash
# Obtenir le PID depuis l'état du conteneur
RUNC_PID=$(sudo runc state nginx-container | jq -r '.pid')

echo "PID du processus runc init : $RUNC_PID"

# Voir les détails du processus
ps aux | grep $RUNC_PID

# Vérifier que c'est bien "runc init"
cat /proc/$RUNC_PID/cmdline | tr '\0' ' '
# Devrait contenir : runc init
```

### Exercice 4.3 : Lister les Conteneurs

```bash
# Lister tous les conteneurs gérés par runc
sudo runc list
```

**Sortie attendue** :
```
ID               PID         STATUS      BUNDLE                           CREATED
nginx-container  12345       created     /home/<username>/mycontainer     2024-01-15T10:30:00Z
```

### Exercice 4.4 : Démarrer le Conteneur

```bash
# Démarrer le conteneur (lance nginx)
sudo runc start nginx-container

# Vérifier l'état
sudo runc state nginx-container
```

**Sortie après start** :
```json
{
  "ociVersion": "1.0.0",
  "id": "nginx-container",
  "pid": 12350,
  "status": "running",
  ...
}
```

**Observation** :
- `status: running` : Le processus nginx tourne maintenant
- Le PID a changé (ce n'est plus runc init, mais nginx)

### Exercice 4.5 : Vérifier que Nginx Tourne

```bash
# Voir le processus nginx
ps aux | grep nginx

# Lister à nouveau les conteneurs
sudo runc list

# Voir les logs (si disponibles)
sudo runc events nginx-container
```

---

## Partie 5 : Configurer le Réseau du Conteneur

Par défaut, le conteneur n'a accès qu'à l'interface `lo` (loopback). Pour accéder à Nginx depuis l'hôte, nous devons configurer le réseau.

### Exercice 5.1 : Vérifier l'Isolation Réseau

```bash
# Obtenir le PID du conteneur
CONTAINER_PID=$(sudo runc state nginx-container | jq -r '.pid')

# Lister les interfaces réseau du conteneur
sudo nsenter -t $CONTAINER_PID -n ip addr show

# Sortie attendue :
# 1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536
#     inet 127.0.0.1/8 scope host lo
```

**Problème** : Pas d'interface réseau autre que loopback → Nginx n'est pas accessible.

### Exercice 5.2 : Créer une Paire veth

Une **paire veth (virtual ethernet)** est comme un câble Ethernet virtuel avec deux extrémités :
- Une extrémité reste sur l'hôte
- L'autre est déplacée dans le network namespace du conteneur

```bash
# Créer une paire veth
sudo ip link add veth0 type veth peer name veth1

# Vérifier
ip link show | grep veth
```

### Exercice 5.3 : Configurer l'Extrémité Hôte (veth0)

```bash
# Assigner une IP à veth0 (côté hôte)
sudo ip addr add 192.168.0.1/24 dev veth0

# Activer l'interface
sudo ip link set veth0 up

# Vérifier
ip addr show veth0
```

### Exercice 5.4 : Déplacer veth1 dans le Conteneur

```bash
# Obtenir le PID du conteneur
CONTAINER_PID=$(sudo runc state nginx-container | jq -r '.pid')

# Créer un lien symbolique pour ip netns
# (workaround car runc ne crée pas automatiquement dans /run/netns)
sudo mkdir -p /run/netns
sudo ln -sf /proc/$CONTAINER_PID/ns/net /run/netns/nginx-container

# Déplacer veth1 dans le network namespace du conteneur
sudo ip link set veth1 netns nginx-container

# Vérifier que veth1 a disparu de l'hôte
ip link show | grep veth1
# Ne devrait rien retourner
```

### Exercice 5.5 : Configurer l'Extrémité Conteneur (veth1)

```bash
# Configurer veth1 dans le conteneur
sudo ip netns exec nginx-container ip addr add 192.168.0.2/24 dev veth1
sudo ip netns exec nginx-container ip link set veth1 up

# Activer aussi lo (important pour localhost)
sudo ip netns exec nginx-container ip link set lo up

# Vérifier
sudo ip netns exec nginx-container ip addr show
```

**Sortie attendue** :
```
1: lo: <LOOPBACK,UP,LOWER_UP>
    inet 127.0.0.1/8 scope host lo

5: veth1@if4: <BROADCAST,MULTICAST,UP,LOWER_UP>
    inet 192.168.0.2/24 scope global veth1
```

### Exercice 5.6 : Tester la Connectivité

```bash
# Depuis l'hôte, pinger le conteneur
ping -c 3 192.168.0.2

# Depuis le conteneur, pinger l'hôte
sudo ip netns exec nginx-container ping -c 3 192.168.0.1
```

---

## Partie 6 : Accéder à Nginx

### Exercice 6.1 : Tester Nginx avec curl

```bash
# Requête HTTP depuis l'hôte
curl http://192.168.0.2

# Sortie attendue :
# <!DOCTYPE html>
# <html>
# <head>
# <title>Welcome to nginx!</title>
# ...
```

**✅ Succès !** Nginx est accessible depuis l'hôte via le réseau virtuel.

### Exercice 6.2 : Vérifier les Logs de Nginx

```bash
# Exécuter une commande dans le conteneur pour voir les logs
sudo runc exec nginx-container cat /var/log/nginx/access.log

# Ou voir les processus nginx
sudo runc exec nginx-container ps aux
```

---

## Partie 7 : Gérer le Cycle de Vie du Conteneur

### Exercice 7.1 : Exécuter des Commandes dans le Conteneur

```bash
# Lister les fichiers dans le conteneur
sudo runc exec nginx-container ls -l /

# Voir la version de nginx
sudo runc exec nginx-container nginx -v

# Voir les processus
sudo runc exec nginx-container ps aux

# Ouvrir un shell interactif (si besoin)
sudo runc exec -t nginx-container /bin/sh
```

### Exercice 7.2 : Arrêter le Conteneur

```bash
# Envoyer SIGTERM (arrêt gracieux)
sudo runc kill nginx-container TERM

# Attendre quelques secondes
sleep 3

# Vérifier l'état
sudo runc state nginx-container
# status devrait être "stopped"

# Si le conteneur ne s'arrête pas, forcer avec SIGKILL
sudo runc kill nginx-container KILL
```

### Exercice 7.3 : Supprimer le Conteneur

```bash
# Supprimer le conteneur
sudo runc delete nginx-container

# Vérifier qu'il n'existe plus
sudo runc list

# Nettoyer le lien symbolique netns
sudo rm /run/netns/nginx-container
```

---

## Partie 8 : Optimiser avec runc run

La commande `runc run` combine `create` + `start` en une seule opération.

### Exercice 8.1 : Lancer un Conteneur en Une Commande

```bash
# Se positionner dans le bundle
cd ~/mycontainer

# Lancer le conteneur en mode détaché (-d)
sudo runc run -d nginx-container-2

# Vérifier
sudo runc list
```

**Note** : `runc run` est pratique pour les tests rapides, mais en production, containerd et CRI-O utilisent `create` + `start` séparément pour avoir plus de contrôle.

---

## Partie 9 : Personnaliser la Configuration OCI

### Exercice 9.1 : Limiter la Mémoire

```bash
# Éditer config.json
jq '.linux.resources.memory.limit = 268435456' config.json > config.tmp && mv config.tmp config.json
# 268435456 bytes = 256 MB

# Vérifier
jq '.linux.resources.memory' config.json
```

### Exercice 9.2 : Limiter le CPU

```bash
# Limiter à 50% d'un CPU (quota)
jq '.linux.resources.cpu.quota = 50000' config.json > config.tmp && mv config.tmp config.json
jq '.linux.resources.cpu.period = 100000' config.json > config.tmp && mv config.tmp config.json

# Vérifier
jq '.linux.resources.cpu' config.json
```

### Exercice 9.3 : Ajouter des Variables d'Environnement

```bash
# Ajouter une variable d'environnement
jq '.process.env += ["MY_VAR=hello"]' config.json > config.tmp && mv config.tmp config.json

# Vérifier
jq '.process.env' config.json
```

### Exercice 9.4 : Ajouter un Volume

```bash
# Créer un répertoire sur l'hôte
mkdir -p ~/nginx-data
echo "<h1>Hello from volume!</h1>" > ~/nginx-data/index.html

# Ajouter un montage dans config.json
jq '.mounts += [{
  "destination": "/usr/share/nginx/html",
  "type": "bind",
  "source": "'$HOME'/nginx-data",
  "options": ["rbind", "rw"]
}]' config.json > config.tmp && mv config.tmp config.json

# Vérifier
jq '.mounts[] | select(.destination == "/usr/share/nginx/html")' config.json
```

### Exercice 9.5 : Tester les Modifications

```bash
# Supprimer l'ancien conteneur si nécessaire
sudo runc delete nginx-container-2 2>/dev/null || true

# Lancer avec la nouvelle configuration
sudo runc run -d nginx-container-3

# Configurer le réseau (répéter les étapes de la Partie 5)
CONTAINER_PID=$(sudo runc state nginx-container-3 | jq -r '.pid')
sudo ip link add veth2 type veth peer name veth3
sudo ip addr add 192.168.0.1/24 dev veth2
sudo ip link set veth2 up
sudo mkdir -p /run/netns
sudo ln -sf /proc/$CONTAINER_PID/ns/net /run/netns/nginx-container-3
sudo ip link set veth3 netns nginx-container-3
sudo ip netns exec nginx-container-3 ip addr add 192.168.0.2/24 dev veth3
sudo ip netns exec nginx-container-3 ip link set veth3 up
sudo ip netns exec nginx-container-3 ip link set lo up

# Tester le volume
curl http://192.168.0.2
# Devrait afficher : <h1>Hello from volume!</h1>
```

---

## Partie 10 : Comprendre les Spécifications OCI

### Exercice 10.1 : Analyser config.json Section par Section

```bash
# Version OCI
jq '.ociVersion' config.json

# Processus
jq '.process' config.json

# Root filesystem
jq '.root' config.json

# Hostname
jq '.hostname' config.json

# Mounts
jq '.mounts' config.json

# Namespaces Linux
jq '.linux.namespaces' config.json

# Ressources (cgroups)
jq '.linux.resources' config.json
```

### Exercice 10.2 : Namespaces Disponibles

```bash
# Lister tous les namespaces configurés
jq '.linux.namespaces[].type' config.json

# Sortie typique :
# "pid"
# "network"
# "ipc"
# "uts"
# "mount"
# "cgroup"
```

**Note** : `user` namespace n'est pas activé par défaut (rootless containers).

---

## Partie 11 : Debugging et Troubleshooting

### Exercice 11.1 : Voir les Événements du Conteneur

```bash
# Surveiller les événements en temps réel
sudo runc events nginx-container-3

# Dans un autre terminal, effectuer des actions (exec, kill, etc.)
# et observer les événements
```

### Exercice 11.2 : Inspecter les Cgroups

```bash
# Trouver le cgroup du conteneur
CONTAINER_PID=$(sudo runc state nginx-container-3 | jq -r '.pid')

cat /proc/$CONTAINER_PID/cgroup

# Voir les limites de mémoire
cat /sys/fs/cgroup/system.slice/.../memory.max
```

### Exercice 11.3 : Voir les Namespaces

```bash
# Lister les namespaces du processus
ls -l /proc/$CONTAINER_PID/ns/

# Comparer avec les namespaces de l'hôte
ls -l /proc/$$/ns/
```

---

## Partie 12 : Script Complet d'Automatisation

### Exercice 12.1 : Créer un Script de Gestion

Créez un fichier `runc-manager.sh` :

```bash
#!/bin/bash
set -e

CONTAINER_NAME="nginx-demo"
BUNDLE_DIR="$HOME/${CONTAINER_NAME}-bundle"
IMAGE="nginx:latest"

function create_bundle() {
    echo "📦 Création du bundle..."
    mkdir -p "$BUNDLE_DIR/rootfs"
    cd "$BUNDLE_DIR"
    
    # Extraire l'image
    crane export "$IMAGE" | tar -xC rootfs/
    
    # Générer config.json
    runc spec
    
    # Configurer pour nginx
    jq '.process.terminal = false' config.json > tmp && mv tmp config.json
    jq '.process.args = ["nginx", "-g", "daemon off;"]' config.json > tmp && mv tmp config.json
    
    echo "✅ Bundle créé dans $BUNDLE_DIR"
}

function start_container() {
    echo "🚀 Démarrage du conteneur..."
    cd "$BUNDLE_DIR"
    sudo runc run -d "$CONTAINER_NAME"
    
    sleep 2
    
    # Configuration réseau
    setup_network
    
    echo "✅ Conteneur démarré"
    sudo runc list
}

function setup_network() {
    echo "🌐 Configuration du réseau..."
    
    CONTAINER_PID=$(sudo runc state "$CONTAINER_NAME" | jq -r '.pid')
    
    # Créer veth pair
    sudo ip link add veth0 type veth peer name veth1
    sudo ip addr add 192.168.100.1/24 dev veth0
    sudo ip link set veth0 up
    
    # Déplacer veth1 dans le conteneur
    sudo mkdir -p /run/netns
    sudo ln -sf /proc/$CONTAINER_PID/ns/net /run/netns/$CONTAINER_NAME
    sudo ip link set veth1 netns $CONTAINER_NAME
    
    # Configurer dans le conteneur
    sudo ip netns exec $CONTAINER_NAME ip addr add 192.168.100.2/24 dev veth1
    sudo ip netns exec $CONTAINER_NAME ip link set veth1 up
    sudo ip netns exec $CONTAINER_NAME ip link set lo up
    
    echo "✅ Réseau configuré : http://192.168.100.2"
}

function stop_container() {
    echo "🛑 Arrêt du conteneur..."
    sudo runc kill "$CONTAINER_NAME" TERM
    sleep 2
    sudo runc delete "$CONTAINER_NAME"
    sudo rm -f /run/netns/$CONTAINER_NAME
    echo "✅ Conteneur arrêté"
}

function clean() {
    echo "🧹 Nettoyage..."
    stop_container 2>/dev/null || true
    rm -rf "$BUNDLE_DIR"
    sudo ip link delete veth0 2>/dev/null || true
    echo "✅ Nettoyage terminé"
}

function test() {
    echo "🧪 Test de nginx..."
    curl -s http://192.168.100.2 | head -5
}

case "${1:-}" in
    create)
        create_bundle
        ;;
    start)
        start_container
        ;;
    stop)
        stop_container
        ;;
    clean)
        clean
        ;;
    test)
        test
        ;;
    *)
        echo "Usage: $0 {create|start|stop|clean|test}"
        echo ""
        echo "Workflow complet :"
        echo "  $0 create  # Créer le bundle"
        echo "  $0 start   # Démarrer le conteneur"
        echo "  $0 test    # Tester nginx"
        echo "  $0 stop    # Arrêter le conteneur"
        echo "  $0 clean   # Nettoyer tout"
        exit 1
        ;;
esac
```

### Utilisation

```bash
# Rendre exécutable
chmod +x runc-manager.sh

# Workflow complet
./runc-manager.sh create
./runc-manager.sh start
./runc-manager.sh test
./runc-manager.sh stop
./runc-manager.sh clean
```

---

## Partie 13 : Défis Avancés

### Défi 1 : Conteneur Multi-Processus

**Objectif** : Créer un conteneur qui lance plusieurs services.

**Indice** : Utiliser un script d'init custom dans `process.args`.

### Défi 2 : Conteneur Rootless

**Objectif** : Lancer runc sans root.

```bash
# Installer rootless kit
sudo apt install -y uidmap

# Configurer les subuid/subgid
echo "$USER:100000:65536" | sudo tee -a /etc/subuid
echo "$USER:100000:65536" | sudo tee -a /etc/subgid

# Modifier config.json pour activer user namespace
jq '.linux.namespaces += [{"type": "user"}]' config.json > tmp && mv tmp config.json
jq '.linux.uidMappings = [{"containerID": 0, "hostID": 100000, "size": 65536}]' config.json > tmp && mv tmp config.json
jq '.linux.gidMappings = [{"containerID": 0, "hostID": 100000, "size": 65536}]' config.json > tmp && mv tmp config.json

# Lancer sans sudo
runc run mycontainer
```

### Défi 3 : Logging Avancé

**Objectif** : Capturer stdout/stderr dans des fichiers de log.

```bash
# Modifier process pour rediriger les logs
jq '.process.args = ["sh", "-c", "nginx -g \"daemon off;\" 2>&1 | tee /var/log/nginx.log"]' config.json > tmp && mv tmp config.json
```

---

## Comparaison : runc vs Docker vs Workshop Précédent

| Aspect | Workshop From Scratch | runc | Docker |
|--------|----------------------|------|--------|
| **Complexité** | Très élevée (manuel) | Moyenne | Faible |
| **Namespaces** | Création manuelle avec unshare | Géré par config.json | Automatique |
| **Configuration** | Scripts bash | config.json (OCI) | Dockerfile + CLI |
| **Réseau** | ip/netns manuel | ip/netns manuel | Automatique (bridge) |
| **Images** | Extraction tar | Extraction tar | Pull automatique |
| **Production** | ❌ Éducatif | ✅ Utilisé en production | ✅ Standard industrie |
| **Niveau** | Kernel-level | Runtime-level | User-level |

---

## Résumé et Enseignements

### Ce que Vous Avez Appris

1. **runc** est le runtime de bas niveau standard (OCI)
2. **Bundle OCI** = `rootfs/` + `config.json`
3. **Workflow** : create → start → exec → kill → delete
4. **config.json** permet de configurer finement le conteneur
5. **Réseau** nécessite une configuration manuelle (veth pairs)
6. **Spécifications OCI** définissent un standard inter-opérable

### Différences Clés avec Docker

Docker = High-level abstraction qui utilise containerd qui utilise runc

```
docker run nginx
     ↓
dockerd (API + Image management)
     ↓
containerd (Lifecycle management)
     ↓
containerd-shim (Process supervisor)
     ↓
runc (OCI runtime)
     ↓
Nginx process (dans namespaces)
```

### Avantages de runc

- **Standard OCI** : Interopérable avec tout l'écosystème
- **Léger** : Pas de daemon, juste un CLI
- **Contrôle fin** : Configuration détaillée via config.json
- **Production-ready** : Utilisé par Docker, Kubernetes, etc.

---

## Prochaines Étapes

1. **Explorer containerd** : Niveau au-dessus de runc
2. **Kubernetes** : Comprendre comment kubelet utilise CRI + runc
3. **Sécurité** : Implémenter seccomp, AppArmor dans config.json
4. **Networking avancé** : CNI plugins, bridge networks
5. **Monitoring** : Intégrer avec cgroups v2 metrics

---

## Nettoyage

```bash
# Supprimer tous les conteneurs
sudo runc list | tail -n +2 | awk '{print $1}' | xargs -r sudo runc delete

# Nettoyer les interfaces réseau
sudo ip link delete veth0 2>/dev/null || true
sudo ip link delete veth2 2>/dev/null || true

# Nettoyer les symlinks netns
sudo rm -rf /run/netns/*

# Supprimer les bundles
rm -rf ~/mycontainer
rm -rf ~/nginx-demo-bundle
```

---

## Ressources Complémentaires

### Documentation Officielle
- [runc GitHub](https://github.com/opencontainers/runc)
- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec)
- [OCI Image Specification](https://github.com/opencontainers/image-spec)

### Commandes Utiles

```bash
# Générer une spec avec template
runc spec --rootless

# Lancer en mode debug
runc --debug run mycontainer

# Voir la version OCI supportée
runc --version

# Générer une spec minimale
runc spec --bundle /path/to/bundle

# Checkpoint/restore (CRIU)
runc checkpoint mycontainer
runc restore mycontainer
```

---

## Glossaire

- **Bundle** : Répertoire contenant rootfs/ et config.json
- **OCI** : Open Container Initiative - standards pour conteneurs
- **runc init** : Processus stub qui tient les namespaces avant le start
- **veth pair** : Paire d'interfaces réseau virtuelles connectées
- **config.json** : Fichier de configuration OCI du conteneur
- **CRI** : Container Runtime Interface (API Kubernetes)

---

*Workshop créé pour des professionnels IT français apprenant Docker et les technologies de conteneurisation.*
