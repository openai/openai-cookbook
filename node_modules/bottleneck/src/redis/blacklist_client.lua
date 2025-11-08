local blacklist = ARGV[num_static_argv + 1]

if redis.call('zscore', client_last_seen_key, blacklist) then
  redis.call('zadd', client_last_seen_key, 0, blacklist)
end


return {}
