local index = ARGV[num_static_argv + 1]

redis.call('zadd', job_expirations_key, 0, index)

return process_tick(now, false)['running']
