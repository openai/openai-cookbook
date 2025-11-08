local index = ARGV[num_static_argv + 1]
local weight = tonumber(ARGV[num_static_argv + 2])
local expiration = tonumber(ARGV[num_static_argv + 3])

local state = process_tick(now, false)
local capacity = state['capacity']
local reservoir = state['reservoir']

local settings = redis.call('hmget', settings_key,
  'nextRequest',
  'minTime',
  'groupTimeout'
)
local nextRequest = tonumber(settings[1])
local minTime = tonumber(settings[2])
local groupTimeout = tonumber(settings[3])

if conditions_check(capacity, weight) then

  redis.call('hincrby', settings_key, 'running', weight)
  redis.call('hset', job_weights_key, index, weight)
  if expiration ~= nil then
    redis.call('zadd', job_expirations_key, now + expiration, index)
  end
  redis.call('hset', job_clients_key, index, client)
  redis.call('zincrby', client_running_key, weight, client)
  redis.call('hincrby', client_num_queued_key, client, -1)
  redis.call('zadd', client_last_registered_key, now, client)

  local wait = math.max(nextRequest - now, 0)
  local newNextRequest = now + wait + minTime

  if reservoir == nil then
    redis.call('hset', settings_key,
      'nextRequest', newNextRequest
    )
  else
    reservoir = reservoir - weight
    redis.call('hmset', settings_key,
      'reservoir', reservoir,
      'nextRequest', newNextRequest
    )
  end

  refresh_expiration(now, newNextRequest, groupTimeout)

  return {true, wait, reservoir}

else
  return {false}
end
