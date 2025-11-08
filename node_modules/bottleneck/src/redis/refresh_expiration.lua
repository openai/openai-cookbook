local refresh_expiration = function (now, nextRequest, groupTimeout)

  if groupTimeout ~= nil then
    local ttl = (nextRequest + groupTimeout) - now

    for i = 1, #KEYS do
      redis.call('pexpire', KEYS[i], ttl)
    end
  end

end
