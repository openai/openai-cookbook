local weight = tonumber(ARGV[num_static_argv + 1])

local capacity = process_tick(now, false)['capacity']
local nextRequest = tonumber(redis.call('hget', settings_key, 'nextRequest'))

return conditions_check(capacity, weight) and nextRequest - now <= 0
