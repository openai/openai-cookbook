local queued = tonumber(ARGV[num_static_argv + 1])

-- Could have been re-registered concurrently
if not redis.call('zscore', client_last_seen_key, client) then
  redis.call('zadd', client_running_key, 0, client)
  redis.call('hset', client_num_queued_key, client, queued)
  redis.call('zadd', client_last_registered_key, 0, client)
end

redis.call('zadd', client_last_seen_key, now, client)

return {}
