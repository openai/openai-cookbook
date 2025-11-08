process_tick(now, false)

return tonumber(redis.call('hget', settings_key, 'done'))
