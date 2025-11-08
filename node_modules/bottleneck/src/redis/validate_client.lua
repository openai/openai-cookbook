if not redis.call('zscore', client_last_seen_key, client) then
  return redis.error_reply('UNKNOWN_CLIENT')
end

redis.call('zadd', client_last_seen_key, now, client)
