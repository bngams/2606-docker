import os
import redis
from flask import Flask

app = Flask(__name__)
cache = redis.Redis(
    host=os.getenv("REDIS_HOST", "redis"),
    port=int(os.getenv("REDIS_PORT", "6379")),
)

@app.route("/")
def hello():
    # Increment the hit counter in Redis and return a message with the count
    count = cache.incr("hits")
    return f"Hello Hello me from Docker! I have been seen {count} time(s)!!!\n"