# Workshop : Construire un Conteneur From Scratch sur Linux

## Objectif

Dans ce workshop, vous allez créer manuellement un conteneur Linux en utilisant uniquement des outils standard du noyau : `unshare`, `mount`, et `pivot_root`. Pas de Docker, pas de containerd, pas de runc - juste vous et le noyau Linux.

Ce workshop vous permettra de comprendre **réellement** comment fonctionnent les conteneurs sous le capot.

## Ressources

Ce workshop s'inspire du tutoriel :
- [How Container Filesystem Works: Building a Docker-like Container From Scratch](https://labs.iximiuz.com/tutorials/container-filesystem-from-scratch)

## Prérequis

- Une machine Debian Linux (VM ou machine physique)
- Accès root via `sudo`
- Connaissances de base en ligne de commande Linux
- Avoir lu le document théorique sur l'architecture des conteneurs

## Préparation de l'Environnement

### Vérification du système

```bash
# Vérifier la version du noyau (>= 4.0 recommandé)
uname -r

# Vérifier que les namespaces sont disponibles
ls /proc/$$/ns/

# Installer les outils nécessaires
sudo apt update
sudo apt install -y \
    coreutils \
    util-linux \
    curl \
    wget \
    ca-certificates
```

### Installer l'outil crane (pour extraire les images)

```bash
# Télécharger et installer crane
curl -sL "https://github.com/google/go-containerregistry/releases/download/v0.19.0/go-containerregistry_Linux_x86_64.tar.gz" | \
sudo tar -C /usr/local/bin -xzf - crane

# Vérifier l'installation
crane version
```

---

## Partie 1 : Comprendre les Mount Namespaces

### Exercice 1.1 : Explorer les Mount Namespaces

**Objectif** : Comprendre ce que les mount namespaces isolent réellement.

#### Terminal 1

```bash
# Créer un nouveau shell dans un mount namespace séparé
sudo unshare --mount bash

# Vérifier le namespace mount actuel
readlink /proc/self/ns/mnt
# Notez l'inode number
```

#### Terminal 2 (hôte)

```bash
# Créer un fichier marqueur sur l'hôte
echo "Hello from host's mount namespace" | sudo tee /opt/marker.txt
```

#### Retour Terminal 1

```bash
# Essayer de voir le fichier
cat /opt/marker.txt
# ✅ Le fichier est visible ! Pourquoi ?
```

**Question** : Qu'est-ce qui est réellement isolé par le mount namespace ?

<details>
<summary>💡 Réponse</summary>

Les mount namespaces isolent la **table de montage** (mount table), pas le système de fichiers lui-même. Les fichiers restent visibles jusqu'à ce que vous créiez des points de montage différents.
</details>

#### Créer un nouveau montage dans le namespace

```bash
# Dans Terminal 1 (namespace isolé)
sudo mount --bind /tmp /mnt

# Lister le contenu de /mnt
ls -l /mnt
# Vous devriez voir le contenu de /tmp

# Vérifier la table de montage
findmnt | grep /mnt
```

#### Dans Terminal 2 (hôte)

```bash
# Vérifier que /mnt est vide sur l'hôte
ls -l /mnt

# Comparer les tables de montage
findmnt | grep /mnt
# /mnt ne devrait PAS apparaître dans la table de montage de l'hôte
```

**Conclusion** : Les mount namespaces isolent les **points de montage**, pas les fichiers.

---

## Partie 2 : Mount Propagation

### Exercice 2.1 : Observer la Propagation de Mount

**Objectif** : Comprendre comment les événements de montage peuvent se propager entre namespaces.

#### Programme Go simple (unshare_lite.go)

```go
package main

import (
    "os"
    "os/exec"
    "syscall"
)

func main() {
    // Créer un nouveau mount namespace
    if err := syscall.Unshare(syscall.CLONE_NEWNS); err != nil {
        panic(err)
    }
    
    // Lancer bash dans ce namespace
    cmd := exec.Command("bash")
    cmd.Stdin = os.Stdin
    cmd.Stdout = os.Stdout
    cmd.Stderr = os.Stderr
    cmd.Env = os.Environ()
    cmd.Run()
}
```

#### Compiler et exécuter

```bash
# Si vous avez Go installé
go build -o unshare_lite unshare_lite.go

# Sinon, continuez avec la commande unshare standard
```

#### Terminal 1

```bash
# Avec Go (propagation activée par défaut)
sudo ./unshare_lite

# OU avec unshare standard (propagation désactivée)
sudo unshare --mount --propagation private bash
```

#### Monter quelque chose

```bash
# Dans Terminal 1
mount --bind /tmp /mnt
ls -l /mnt
```

#### Terminal 2

```bash
# Vérifier si le montage est visible sur l'hôte
ls -l /mnt

# Comparer les tables de montage
findmnt | grep /mnt
```

**Observation** :
- Avec `unshare` standard : Le montage est isolé (type de propagation = `private`)
- Avec le syscall direct Go : Le montage peut être propagé (type = `shared` par défaut)

### Exercice 2.2 : Comprendre les Types de Propagation

```bash
# Créer un nouveau namespace avec propagation privée
sudo unshare --mount --propagation private bash

# Vérifier les types de propagation
findmnt -o TARGET,SOURCE,FSTYPE,PROPAGATION

# Vous devriez voir "private" pour tous les montages
```

**Types de propagation** :
- `shared` : Les événements de montage sont propagés aux namespaces pairs
- `private` : Aucune propagation (isolation totale)
- `slave` : Reçoit les événements du master, mais ne propage pas
- `unbindable` : Ne peut pas être bind-mounted

---

## Partie 3 : Créer un Conteneur Naïf

### Exercice 3.1 : Préparer le Root Filesystem du Conteneur

```bash
# Créer un répertoire pour le conteneur
sudo mkdir -p /opt/container-1/rootfs

# Extraire le système de fichiers d'Alpine Linux
crane export alpine:3 | sudo tar -xvC /opt/container-1/rootfs

# Explorer le contenu
tree -L 1 /opt/container-1/rootfs
```

**Observation** : Le répertoire ressemble à un système Linux complet !

```bash
# Comparer avec l'OS de l'hôte
cat /etc/os-release

# Comparer avec l'OS du conteneur
cat /opt/container-1/rootfs/etc/os-release
```

### Exercice 3.2 : Utiliser pivot_root pour Changer de Root

**Objectif** : Basculer vers le nouveau système de fichiers.

```bash
# Créer un nouveau mount namespace
sudo unshare --mount bash

# Rendre la propagation privée
mount --make-rprivate /

# Créer un point de montage pour le rootfs
mount --rbind /opt/container-1/rootfs /opt/container-1/rootfs

# S'assurer que le type de propagation n'est pas shared
mount --make-rprivate /opt/container-1/rootfs

# Se déplacer dans le répertoire rootfs
cd /opt/container-1/rootfs

# Créer un répertoire pour l'ancien root
mkdir .oldroot

# Pivoter vers le nouveau root
pivot_root . .oldroot

# Basculer vers le shell du nouveau rootfs
exec /bin/sh

# Maintenant, vous êtes "dans le conteneur" !
ls -l /

# Vérifier l'OS
cat /etc/os-release
# Vous devriez voir Alpine Linux
```

### Exercice 3.3 : Nettoyer l'Ancien Root

```bash
# Démonter l'ancien root (lazy unmount)
umount -l .oldroot

# Supprimer le répertoire
rm -rf .oldroot

# Vérifier qu'il a disparu
ls -la /
```

### Exercice 3.4 : Tester les Commandes

```bash
# Essayer quelques commandes
ps aux
# ⚠️ Vide ! Pourquoi ?

df -h
# ⚠️ Erreur : /proc/mounts n'existe pas

ls -l /proc
# Vide !
```

**Problème** : Les pseudo-filesystems `/proc`, `/dev`, `/sys` ne sont pas montés.

---

## Partie 4 : Monter les Pseudo-Filesystems

### Exercice 4.1 : Monter /proc

**Objectif** : Permettre aux commandes comme `ps` de fonctionner.

```bash
# Monter le pseudo-filesystem proc
mount -t proc proc /proc

# Tester la commande ps
ps aux
# ⚠️ Vous voyez TOUS les processus de l'hôte !
```

**Question** : Comment isoler les processus ?

<details>
<summary>💡 Réponse</summary>

Il faut créer un **PID namespace** en plus du mount namespace. Nous verrons ça dans la Partie 5.
</details>

### Exercice 4.2 : Monter /dev

```bash
# Créer le répertoire /dev s'il n'existe pas
mkdir -p /dev

# Monter un tmpfs pour /dev
mount -t tmpfs -o nosuid,strictatime,mode=0755,size=65536k tmpfs /dev

# Créer les devices caractères standards
mknod -m 666 /dev/null c 1 3
mknod -m 666 /dev/zero c 1 5
mknod -m 666 /dev/full c 1 7
mknod -m 666 /dev/random c 1 8
mknod -m 666 /dev/urandom c 1 9
mknod -m 666 /dev/tty c 5 0

# Définir les bonnes permissions
chown root:root /dev/{null,zero,full,random,urandom,tty}

# Créer les symlinks standards
ln -sf /proc/self/fd /dev/fd
ln -sf /proc/self/fd/0 /dev/stdin
ln -sf /proc/self/fd/1 /dev/stdout
ln -sf /proc/self/fd/2 /dev/stderr
ln -sf /proc/kcore /dev/core

# Monter les sous-filesystems de /dev
mkdir -p /dev/{shm,pts,mqueue}

mount -t tmpfs -o nosuid,nodev,noexec,mode=1777,size=67108864 tmpfs /dev/shm
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts /dev/pts
mount -t mqueue -o nosuid,nodev,noexec mqueue /dev/mqueue

# Créer le symlink ptmx
ln -sf /dev/pts/ptmx /dev/ptmx

# Tester
echo "Hello" > /dev/null
cat /dev/random | head -c 10 | base64
```

### Exercice 4.3 : Monter /sys

```bash
# Monter le pseudo-filesystem sysfs (read-only)
mount -t sysfs -o ro,nosuid,nodev,noexec sysfs /sys

# Vérifier
ls -l /sys

# Monter le cgroup2 filesystem
mkdir -p /sys/fs/cgroup
mount -t cgroup2 -o ro,nosuid,nodev,noexec cgroup2 /sys/fs/cgroup

# Vérifier
ls -l /sys/fs/cgroup
```

---

## Partie 5 : Créer un Conteneur Complet avec Tous les Namespaces

### Exercice 5.1 : Préparer les Fichiers Spéciaux

#### Sur l'Hôte (sortir du conteneur précédent)

```bash
# Appuyez sur Ctrl+D ou tapez exit pour sortir
exit

# Préparer le deuxième conteneur
CONTAINER_DIR=/opt/container-2
ROOTFS_DIR=$CONTAINER_DIR/rootfs

sudo mkdir -p $ROOTFS_DIR

# Extraire Alpine Linux
crane export alpine:3 | sudo tar -xvC $ROOTFS_DIR

# Créer les fichiers /etc spécifiques au conteneur
cat <<EOF | sudo tee $CONTAINER_DIR/hosts
127.0.0.1 localhost container-2
::1 localhost ip6-localhost ip6-loopback
EOF

cat <<EOF | sudo tee $CONTAINER_DIR/hostname
container-2
EOF

sudo cp /etc/resolv.conf $CONTAINER_DIR/resolv.conf
```

### Exercice 5.2 : Créer Tous les Namespaces

```bash
# Créer mount, PID, cgroup, UTS, et network namespaces
sudo unshare --mount --pid --fork --cgroup --uts --net bash

# Vérifier les namespaces
readlink /proc/self/ns/{mnt,pid,cgroup,uts,net}
```

**Explication des flags** :
- `--mount` : Mount namespace (système de fichiers isolé)
- `--pid` : PID namespace (processus isolés, nouveau PID 1)
- `--fork` : Fork avant d'entrer dans le PID namespace
- `--cgroup` : Cgroup namespace (vue isolée des cgroups)
- `--uts` : UTS namespace (hostname isolé)
- `--net` : Network namespace (interfaces réseau isolées)

### Exercice 5.3 : Configurer le Mount Namespace

```bash
# Redéfinir les variables (elles ne sont pas héritées)
CONTAINER_DIR=/opt/container-2
ROOTFS_DIR=$CONTAINER_DIR/rootfs

# Isoler du mount namespace de l'hôte
mount --make-rslave /

# Créer un point de montage pour le rootfs
mount --rbind $ROOTFS_DIR $ROOTFS_DIR

# Rendre privé
mount --make-private $ROOTFS_DIR
```

### Exercice 5.4 : Monter les Pseudo-Filesystems

```bash
# Monter /proc
mkdir -p $ROOTFS_DIR/proc
mount -t proc proc $ROOTFS_DIR/proc

# Monter /dev
mount -t tmpfs -o nosuid,strictatime,mode=0755,size=65536k tmpfs $ROOTFS_DIR/dev

# Créer les devices
mknod -m 666 "$ROOTFS_DIR/dev/null" c 1 3
mknod -m 666 "$ROOTFS_DIR/dev/zero" c 1 5
mknod -m 666 "$ROOTFS_DIR/dev/full" c 1 7
mknod -m 666 "$ROOTFS_DIR/dev/random" c 1 8
mknod -m 666 "$ROOTFS_DIR/dev/urandom" c 1 9
mknod -m 666 "$ROOTFS_DIR/dev/tty" c 5 0

chown root:root "$ROOTFS_DIR/dev/"{null,zero,full,random,urandom,tty}

# Créer les symlinks
ln -sf /proc/self/fd "$ROOTFS_DIR/dev/fd"
ln -sf /proc/self/fd/0 "$ROOTFS_DIR/dev/stdin"
ln -sf /proc/self/fd/1 "$ROOTFS_DIR/dev/stdout"
ln -sf /proc/self/fd/2 "$ROOTFS_DIR/dev/stderr"
ln -sf /proc/kcore "$ROOTFS_DIR/dev/core"

# Créer et monter les sous-filesystems de /dev
mkdir -p "$ROOTFS_DIR/dev/pts"
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts $ROOTFS_DIR/dev/pts
ln -sf /dev/pts/ptmx "$ROOTFS_DIR/dev/ptmx"

mkdir -p "$ROOTFS_DIR/dev/mqueue"
mount -t mqueue -o nosuid,nodev,noexec mqueue $ROOTFS_DIR/dev/mqueue

mkdir -p "$ROOTFS_DIR/dev/shm"
mount -t tmpfs -o nosuid,nodev,noexec,mode=1777,size=67108864 tmpfs $ROOTFS_DIR/dev/shm

# Monter /sys
mkdir -p "$ROOTFS_DIR/sys"
mount -t sysfs -o ro,nosuid,nodev,noexec sysfs $ROOTFS_DIR/sys

mkdir -p "$ROOTFS_DIR/sys/fs/cgroup"
mount -t cgroup2 -o ro,nosuid,nodev,noexec cgroup2 $ROOTFS_DIR/sys/fs/cgroup
```

### Exercice 5.5 : Bind Mount des Fichiers /etc

```bash
# Bind mount des fichiers spécifiques au conteneur
for p in hostname hosts resolv.conf
do
    touch $ROOTFS_DIR/etc/$p
    mount --bind "$CONTAINER_DIR/$p" $ROOTFS_DIR/etc/$p
done
```

### Exercice 5.6 : Pivoter vers le Nouveau Root

```bash
# Se déplacer dans le rootfs
cd $ROOTFS_DIR

# Créer le répertoire pour l'ancien root
mkdir -p .oldroot

# Pivoter
pivot_root . .oldroot

# Exécuter le shell du conteneur
exec /bin/sh

# Configurer la propagation du root
mount --make-rslave /

# Nettoyer l'ancien root
umount -l .oldroot
rmdir .oldroot

# Configurer le hostname
hostname $(cat /etc/hostname)
```

### Exercice 5.7 : Durcir le Filesystem (Security Hardening)

```bash
# Rendre certaines parties de /proc read-only
for d in bus fs irq sys sysrq-trigger
do
    if [ -e "/proc/$d" ]; then
        mount --bind "/proc/$d" "/proc/$d"
        mount -o remount,bind,ro "/proc/$d"
    fi
done

# Masquer les chemins sensibles
for p in \
    /proc/asound \
    /proc/interrupts \
    /proc/kcore \
    /proc/keys \
    /proc/latency_stats \
    /proc/timer_list \
    /proc/timer_stats \
    /proc/sched_debug \
    /proc/acpi \
    /proc/scsi \
    /sys/firmware
do
    if [ -d "$p" ]; then
        # Masquer un répertoire
        mount -t tmpfs -o ro tmpfs $p
    elif [ -f "$p" ]; then
        # Masquer un fichier
        mount --bind /dev/null $p
    fi
done
```

### Exercice 5.8 : Tester le Conteneur

```bash
# Vérifier le hostname
hostname
# Devrait afficher : container-2

# Vérifier l'OS
cat /etc/os-release
# Alpine Linux

# Lister les processus (maintenant isolés !)
ps aux
# Vous ne devriez voir que les processus du conteneur

# Vérifier les interfaces réseau
ip addr show
# Seulement lo (loopback) devrait être présent

# Vérifier les fichiers /etc
cat /etc/hosts
cat /etc/hostname
cat /etc/resolv.conf

# Tester les commandes système
df -h
mount | head -20
top
```

**✅ Félicitations !** Vous avez créé un conteneur complet manuellement !

---

## Partie 6 : Partager des Fichiers avec le Conteneur

### Exercice 6.1 : Bind Mount d'un Répertoire Hôte

**Objectif** : Partager des données entre l'hôte et le conteneur (comme `-v` de Docker).

#### Sur l'Hôte (avant de créer le conteneur)

```bash
# Créer un répertoire partagé
sudo mkdir -p /opt/shared-data
echo "Hello from host!" | sudo tee /opt/shared-data/message.txt
```

#### Lors de la Création du Conteneur

```bash
# Dans le script de création (après avoir monté /proc, /dev, /sys)
# Mais AVANT pivot_root

# Créer le point de montage dans le conteneur
mkdir -p $ROOTFS_DIR/data

# Bind mount du répertoire partagé
mount --bind /opt/shared-data $ROOTFS_DIR/data

# Optionnel : Configurer la propagation
# mount --make-rprivate $ROOTFS_DIR/data  # Pas de propagation
# mount --make-rshared $ROOTFS_DIR/data   # Propagation bidirectionnelle
```

#### Dans le Conteneur

```bash
# Après pivot_root
cat /data/message.txt
# Devrait afficher : Hello from host!

# Créer un fichier depuis le conteneur
echo "Hello from container!" > /data/from-container.txt
```

#### De Retour sur l'Hôte

```bash
# Vérifier que le fichier est visible
cat /opt/shared-data/from-container.txt
```

---

## Partie 7 : Script Complet de Création de Conteneur

### Exercice 7.1 : Créer un Script Réutilisable

Créez un fichier `create_container.sh` :

```bash
#!/bin/bash
set -e

# Configuration
CONTAINER_NAME=${1:-mycontainer}
IMAGE=${2:-alpine:3}
CONTAINER_DIR="/opt/$CONTAINER_NAME"
ROOTFS_DIR="$CONTAINER_DIR/rootfs"

echo "🐳 Création du conteneur : $CONTAINER_NAME"
echo "📦 Image : $IMAGE"

# 1. Préparer le rootfs
echo "📁 Préparation du rootfs..."
sudo mkdir -p "$ROOTFS_DIR"
crane export "$IMAGE" | sudo tar -xC "$ROOTFS_DIR"

# 2. Préparer les fichiers /etc
echo "📝 Création des fichiers /etc..."
cat <<EOF | sudo tee "$CONTAINER_DIR/hosts" > /dev/null
127.0.0.1 localhost $CONTAINER_NAME
::1 localhost ip6-localhost ip6-loopback
EOF

echo "$CONTAINER_NAME" | sudo tee "$CONTAINER_DIR/hostname" > /dev/null
sudo cp /etc/resolv.conf "$CONTAINER_DIR/resolv.conf"

# 3. Créer le script de démarrage
cat <<'SCRIPT' | sudo tee "$CONTAINER_DIR/start.sh" > /dev/null
#!/bin/bash
set -e

CONTAINER_DIR="__CONTAINER_DIR__"
ROOTFS_DIR="$CONTAINER_DIR/rootfs"

# Isoler mount namespace
mount --make-rslave /

# Bind mount rootfs
mount --rbind "$ROOTFS_DIR" "$ROOTFS_DIR"
mount --make-private "$ROOTFS_DIR"

# Monter /proc
mkdir -p "$ROOTFS_DIR/proc"
mount -t proc proc "$ROOTFS_DIR/proc"

# Monter /dev
mount -t tmpfs -o nosuid,strictatime,mode=0755,size=65536k tmpfs "$ROOTFS_DIR/dev"

# Devices
mknod -m 666 "$ROOTFS_DIR/dev/null" c 1 3
mknod -m 666 "$ROOTFS_DIR/dev/zero" c 1 5
mknod -m 666 "$ROOTFS_DIR/dev/random" c 1 8
mknod -m 666 "$ROOTFS_DIR/dev/urandom" c 1 9
mknod -m 666 "$ROOTFS_DIR/dev/tty" c 5 0
chown root:root "$ROOTFS_DIR/dev/"{null,zero,random,urandom,tty}

# Symlinks
ln -sf /proc/self/fd "$ROOTFS_DIR/dev/fd"
ln -sf /proc/self/fd/0 "$ROOTFS_DIR/dev/stdin"
ln -sf /proc/self/fd/1 "$ROOTFS_DIR/dev/stdout"
ln -sf /proc/self/fd/2 "$ROOTFS_DIR/dev/stderr"

# /dev/pts
mkdir -p "$ROOTFS_DIR/dev/pts"
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$ROOTFS_DIR/dev/pts"

# Monter /sys
mkdir -p "$ROOTFS_DIR/sys"
mount -t sysfs -o ro,nosuid,nodev,noexec sysfs "$ROOTFS_DIR/sys"

# Bind mount /etc files
for p in hostname hosts resolv.conf; do
    touch "$ROOTFS_DIR/etc/$p"
    mount --bind "$CONTAINER_DIR/$p" "$ROOTFS_DIR/etc/$p"
done

# Pivot root
cd "$ROOTFS_DIR"
mkdir -p .oldroot
pivot_root . .oldroot
exec /bin/sh -c "
    mount --make-rslave /
    umount -l .oldroot
    rmdir .oldroot
    hostname \$(cat /etc/hostname)
    exec /bin/sh
"
SCRIPT

sudo sed -i "s|__CONTAINER_DIR__|$CONTAINER_DIR|g" "$CONTAINER_DIR/start.sh"
sudo chmod +x "$CONTAINER_DIR/start.sh"

echo "✅ Conteneur créé avec succès !"
echo ""
echo "🚀 Pour démarrer le conteneur :"
echo "   sudo unshare --mount --pid --fork --cgroup --uts --net $CONTAINER_DIR/start.sh"
```

### Utilisation

```bash
# Rendre le script exécutable
chmod +x create_container.sh

# Créer un conteneur
./create_container.sh mon-alpine alpine:3

# Démarrer le conteneur
sudo unshare --mount --pid --fork --cgroup --uts --net /opt/mon-alpine/start.sh
```

---

## Partie 8 : Défis Avancés

### Défi 1 : Limiter la Mémoire avec Cgroups

**Objectif** : Utiliser cgroups v2 pour limiter la mémoire du conteneur.

```bash
# Sur l'hôte, avant de lancer le conteneur

# Créer un cgroup
sudo mkdir -p /sys/fs/cgroup/mycontainer

# Limiter à 256M de RAM
echo "256M" | sudo tee /sys/fs/cgroup/mycontainer/memory.max

# Obtenir le PID du processus init du conteneur
# (après l'avoir démarré dans un autre terminal)
CONTAINER_PID=$(pgrep -f "unshare.*mycontainer")

# Ajouter le processus au cgroup
echo $CONTAINER_PID | sudo tee /sys/fs/cgroup/mycontainer/cgroup.procs

# Vérifier la limite
cat /sys/fs/cgroup/mycontainer/memory.max
```

### Défi 2 : Ajouter une Interface Réseau

**Objectif** : Créer un veth pair et le connecter au conteneur.

```bash
# Sur l'hôte

# Trouver le PID du conteneur
CONTAINER_PID=$(pgrep -f "unshare.*mycontainer")

# Créer un veth pair
sudo ip link add veth0 type veth peer name veth1

# Configurer veth0 sur l'hôte
sudo ip addr add 172.18.0.1/24 dev veth0
sudo ip link set veth0 up

# Déplacer veth1 dans le network namespace du conteneur
sudo ip link set veth1 netns /proc/$CONTAINER_PID/ns/net

# Dans le conteneur (exécuter depuis un autre terminal)
# sudo nsenter -t $CONTAINER_PID -n /bin/sh
ip addr add 172.18.0.2/24 dev veth1
ip link set veth1 up
ip link set lo up

# Tester la connectivité
ping -c 3 172.18.0.1  # Depuis le conteneur
```

### Défi 3 : Créer un Conteneur avec Nginx

**Objectif** : Installer et lancer Nginx dans un conteneur.

```bash
# Utiliser une image nginx
./create_container.sh nginx-container nginx:alpine

# Modifier le script de démarrage pour lancer nginx
# Au lieu de exec /bin/sh, utiliser :
# exec /docker-entrypoint.sh nginx -g 'daemon off;'
```

---

## Résumé et Enseignements

### Ce que Vous Avez Appris

1. **Mount Namespaces** : Isolent la table de montage, pas les fichiers
2. **Mount Propagation** : Contrôle comment les événements de montage se propagent
3. **pivot_root** : Change la racine du système de fichiers de manière sécurisée
4. **Pseudo-filesystems** : `/proc`, `/dev`, `/sys` doivent être montés séparément
5. **Namespaces multiples** : PID, NET, UTS, IPC, CGROUP travaillent ensemble
6. **Security Hardening** : Masquage de chemins sensibles, montages read-only
7. **Partage de données** : Bind mounts permettent de partager des fichiers

### Architecture d'un Conteneur

```
Hôte Linux
│
├── Namespaces (isolation)
│   ├── Mount : Système de fichiers isolé
│   ├── PID   : Processus isolés
│   ├── NET   : Réseau isolé
│   ├── UTS   : Hostname isolé
│   ├── IPC   : IPC isolé
│   └── USER  : Utilisateurs isolés (optionnel)
│
├── Cgroups (limitation de ressources)
│   ├── memory : Limite de RAM
│   ├── cpu    : Limite de CPU
│   └── blkio  : Limite I/O disque
│
└── Rootfs (système de fichiers du conteneur)
    ├── /bin, /usr, /lib, /etc... (depuis l'image)
    ├── /proc (monté depuis l'hôte)
    ├── /dev  (tmpfs + devices)
    └── /sys  (monté depuis l'hôte)
```

### Différences avec Docker

| Aspect | Notre Conteneur Manuel | Docker |
|--------|----------------------|--------|
| **Création** | Scripts bash + unshare | `docker run` |
| **Rootfs** | Extraction manuelle | Gestion automatique via layers |
| **Networking** | Configuration manuelle | Réseaux bridge automatiques |
| **Volumes** | Bind mounts manuels | Volumes gérés |
| **Images** | Tar archives | Format OCI + registry |
| **Isolation** | Tous les namespaces manuels | Gestion automatique |

---

## Prochaines Étapes

1. **Workshop suivant** : Utiliser `runc` pour créer des conteneurs (plus proche de la production)
2. **Approfondir** : Étudier les spécifications OCI
3. **Expérimenter** : Créer des conteneurs avec différentes distributions (Ubuntu, Debian, etc.)
4. **Optimiser** : Ajouter des overlayfs pour le Copy-on-Write
5. **Sécuriser** : Implémenter seccomp, AppArmor

---

## Nettoyage

```bash
# Sortir du conteneur
exit

# Supprimer les répertoires de conteneurs
sudo rm -rf /opt/container-1
sudo rm -rf /opt/container-2
sudo rm -rf /opt/mon-alpine
sudo rm -rf /opt/nginx-container
```

---

## Ressources Complémentaires

- [Man page mount_namespaces(7)](https://man7.org/linux/man-pages/man7/mount_namespaces.7.html)
- [Man page namespaces(7)](https://man7.org/linux/man-pages/man7/namespaces.7.html)
- [Man page unshare(1)](https://man7.org/linux/man-pages/man1/unshare.1.html)
- [Man page pivot_root(2)](https://man7.org/linux/man-pages/man2/pivot_root.2.html)
- [Kernel Doc: Shared Subtrees](https://www.kernel.org/doc/Documentation/filesystems/sharedsubtree.txt)

---

*Workshop créé pour des professionnels IT français apprenant Docker et les technologies de conteneurisation.*
