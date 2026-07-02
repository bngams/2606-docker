# 04 — Solution

Correction complète du cas pratique (à ne regarder qu'en cas de blocage).

```
solution/srv-docker/
├── edge/compose.yaml        # Traefik (port 80 + dashboard 8080), réseau "edge" créé ici
├── app1/
│   ├── html/index.html      # la page statique
│   ├── Dockerfile           # nginx:1.27-alpine + la page
│   └── compose.yaml         # build + labels (PathPrefix /app1 + stripprefix)
└── app2/compose.yaml        # traefik/whoami + labels (PathPrefix /app2 + stripprefix)
```

## Démarrer (dans l'ordre)

```bash
cd srv-docker/edge && docker compose up -d && cd -
cd srv-docker/app1 && docker compose up -d --build && cd -
cd srv-docker/app2 && docker compose up -d && cd -

curl http://localhost/app1     # page nginx d'App1
curl http://localhost/app2     # whoami (voir X-Forwarded-Prefix: /app2)
# dashboard Traefik : http://localhost:8080
```

## Tout arrêter

```bash
for p in app1 app2 edge; do (cd srv-docker/$p && docker compose down -v); done
```

> ⚠️ Le dashboard Traefik est en `--api.insecure=true` (port 8080 en clair) : **DEV uniquement**.
> Le port 80 est le seul point d'entrée public ; les apps n'exposent aucun port.
