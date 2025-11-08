return not (redis.call('exists', settings_key) == 1)
