from redis import from_url

REDIS_URL = 'redis://localhost:6379'
client = from_url(REDIS_URL)
client.ping()