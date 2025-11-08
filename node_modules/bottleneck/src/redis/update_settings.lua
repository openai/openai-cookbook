local args = {'hmset', settings_key}

for i = num_static_argv + 1, #ARGV do
  table.insert(args, ARGV[i])
end

redis.call(unpack(args))

process_tick(now, true)

local groupTimeout = tonumber(redis.call('hget', settings_key, 'groupTimeout'))
refresh_expiration(0, 0, groupTimeout)

return {}
