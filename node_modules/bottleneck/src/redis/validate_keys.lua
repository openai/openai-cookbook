if not (redis.call('exists', settings_key) == 1) then
  return redis.error_reply('SETTINGS_KEY_NOT_FOUND')
end
