import os
import redis
from flask import Flask

app = Flask(__name__)


def _redis_password():
    # 1) fichier secret monté par Compose (prod), 2) repli env (dev), 3) None (pas de mot de passe)
    path = os.getenv("REDIS_PASSWORD_FILE", "/run/secrets/redis_password")
    if os.path.exists(path):
        return open(path).read().strip()
    return os.getenv("REDIS_PASSWORD")


cache = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=_redis_password(),      # lu depuis le secret (prod) ou l'env (dev)
)


@app.route("/")
def hello():
    # Increment the hit counter in Redis and return a message with the count
    count = cache.incr("hits")
    return f"Hello Hello me from Docker! I have been seen {count} time(s)!!!\n"
