local process_tick = function (now, always_publish)

  local compute_capacity = function (maxConcurrent, running, reservoir)
    if maxConcurrent ~= nil and reservoir ~= nil then
      return math.min((maxConcurrent - running), reservoir)
    elseif maxConcurrent ~= nil then
      return maxConcurrent - running
    elseif reservoir ~= nil then
      return reservoir
    else
      return nil
    end
  end

  local settings = redis.call('hmget', settings_key,
    'id',
    'maxConcurrent',
    'running',
    'reservoir',
    'reservoirRefreshInterval',
    'reservoirRefreshAmount',
    'lastReservoirRefresh',
    'reservoirIncreaseInterval',
    'reservoirIncreaseAmount',
    'reservoirIncreaseMaximum',
    'lastReservoirIncrease',
    'capacityPriorityCounter',
    'clientTimeout'
  )
  local id = settings[1]
  local maxConcurrent = tonumber(settings[2])
  local running = tonumber(settings[3])
  local reservoir = tonumber(settings[4])
  local reservoirRefreshInterval = tonumber(settings[5])
  local reservoirRefreshAmount = tonumber(settings[6])
  local lastReservoirRefresh = tonumber(settings[7])
  local reservoirIncreaseInterval = tonumber(settings[8])
  local reservoirIncreaseAmount = tonumber(settings[9])
  local reservoirIncreaseMaximum = tonumber(settings[10])
  local lastReservoirIncrease = tonumber(settings[11])
  local capacityPriorityCounter = tonumber(settings[12])
  local clientTimeout = tonumber(settings[13])

  local initial_capacity = compute_capacity(maxConcurrent, running, reservoir)

  --
  -- Process 'running' changes
  --
  local expired = redis.call('zrangebyscore', job_expirations_key, '-inf', '('..now)

  if #expired > 0 then
    redis.call('zremrangebyscore', job_expirations_key, '-inf', '('..now)

    local flush_batch = function (batch, acc)
      local weights = redis.call('hmget', job_weights_key, unpack(batch))
                      redis.call('hdel',  job_weights_key, unpack(batch))
      local clients = redis.call('hmget', job_clients_key, unpack(batch))
                      redis.call('hdel',  job_clients_key, unpack(batch))

      -- Calculate sum of removed weights
      for i = 1, #weights do
        acc['total'] = acc['total'] + (tonumber(weights[i]) or 0)
      end

      -- Calculate sum of removed weights by client
      local client_weights = {}
      for i = 1, #clients do
        local removed = tonumber(weights[i]) or 0
        if removed > 0 then
          acc['client_weights'][clients[i]] = (acc['client_weights'][clients[i]] or 0) + removed
        end
      end
    end

    local acc = {
      ['total'] = 0,
      ['client_weights'] = {}
    }
    local batch_size = 1000

    -- Compute changes to Zsets and apply changes to Hashes
    for i = 1, #expired, batch_size do
      local batch = {}
      for j = i, math.min(i + batch_size - 1, #expired) do
        table.insert(batch, expired[j])
      end

      flush_batch(batch, acc)
    end

    -- Apply changes to Zsets
    if acc['total'] > 0 then
      redis.call('hincrby', settings_key, 'done', acc['total'])
      running = tonumber(redis.call('hincrby', settings_key, 'running', -acc['total']))
    end

    for client, weight in pairs(acc['client_weights']) do
      redis.call('zincrby', client_running_key, -weight, client)
    end
  end

  --
  -- Process 'reservoir' changes
  --
  local reservoirRefreshActive = reservoirRefreshInterval ~= nil and reservoirRefreshAmount ~= nil
  if reservoirRefreshActive and now >= lastReservoirRefresh + reservoirRefreshInterval then
    reservoir = reservoirRefreshAmount
    redis.call('hmset', settings_key,
      'reservoir', reservoir,
      'lastReservoirRefresh', now
    )
  end

  local reservoirIncreaseActive = reservoirIncreaseInterval ~= nil and reservoirIncreaseAmount ~= nil
  if reservoirIncreaseActive and now >= lastReservoirIncrease + reservoirIncreaseInterval then
    local num_intervals = math.floor((now - lastReservoirIncrease) / reservoirIncreaseInterval)
    local incr = reservoirIncreaseAmount * num_intervals
    if reservoirIncreaseMaximum ~= nil then
      incr = math.min(incr, reservoirIncreaseMaximum - (reservoir or 0))
    end
    if incr > 0 then
      reservoir = (reservoir or 0) + incr
    end
    redis.call('hmset', settings_key,
      'reservoir', reservoir,
      'lastReservoirIncrease', lastReservoirIncrease + (num_intervals * reservoirIncreaseInterval)
    )
  end

  --
  -- Clear unresponsive clients
  --
  local unresponsive = redis.call('zrangebyscore', client_last_seen_key, '-inf', (now - clientTimeout))
  local unresponsive_lookup = {}
  local terminated_clients = {}
  for i = 1, #unresponsive do
    unresponsive_lookup[unresponsive[i]] = true
    if tonumber(redis.call('zscore', client_running_key, unresponsive[i])) == 0 then
      table.insert(terminated_clients, unresponsive[i])
    end
  end
  if #terminated_clients > 0 then
    redis.call('zrem', client_running_key,         unpack(terminated_clients))
    redis.call('hdel', client_num_queued_key,      unpack(terminated_clients))
    redis.call('zrem', client_last_registered_key, unpack(terminated_clients))
    redis.call('zrem', client_last_seen_key,       unpack(terminated_clients))
  end

  --
  -- Broadcast capacity changes
  --
  local final_capacity = compute_capacity(maxConcurrent, running, reservoir)

  if always_publish or (initial_capacity ~= nil and final_capacity == nil) then
    -- always_publish or was not unlimited, now unlimited
    redis.call('publish', 'b_'..id, 'capacity:'..(final_capacity or ''))

  elseif initial_capacity ~= nil and final_capacity ~= nil and final_capacity > initial_capacity then
    -- capacity was increased
    -- send the capacity message to the limiter having the lowest number of running jobs
    -- the tiebreaker is the limiter having not registered a job in the longest time

    local lowest_concurrency_value = nil
    local lowest_concurrency_clients = {}
    local lowest_concurrency_last_registered = {}
    local client_concurrencies = redis.call('zrange', client_running_key, 0, -1, 'withscores')

    for i = 1, #client_concurrencies, 2 do
      local client = client_concurrencies[i]
      local concurrency = tonumber(client_concurrencies[i+1])

      if (
        lowest_concurrency_value == nil or lowest_concurrency_value == concurrency
      ) and (
        not unresponsive_lookup[client]
      ) and (
        tonumber(redis.call('hget', client_num_queued_key, client)) > 0
      ) then
        lowest_concurrency_value = concurrency
        table.insert(lowest_concurrency_clients, client)
        local last_registered = tonumber(redis.call('zscore', client_last_registered_key, client))
        table.insert(lowest_concurrency_last_registered, last_registered)
      end
    end

    if #lowest_concurrency_clients > 0 then
      local position = 1
      local earliest = lowest_concurrency_last_registered[1]

      for i,v in ipairs(lowest_concurrency_last_registered) do
        if v < earliest then
          position = i
          earliest = v
        end
      end

      local next_client = lowest_concurrency_clients[position]
      redis.call('publish', 'b_'..id,
        'capacity-priority:'..(final_capacity or '')..
        ':'..next_client..
        ':'..capacityPriorityCounter
      )
      redis.call('hincrby', settings_key, 'capacityPriorityCounter', '1')
    else
      redis.call('publish', 'b_'..id, 'capacity:'..(final_capacity or ''))
    end
  end

  return {
    ['capacity'] = final_capacity,
    ['running'] = running,
    ['reservoir'] = reservoir
  }
end
