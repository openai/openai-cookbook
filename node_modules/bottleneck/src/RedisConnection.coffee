parser = require "./parser"
Events = require "./Events"
Scripts = require "./Scripts"

class RedisConnection
  datastore: "redis"
  defaults:
    Redis: null
    clientOptions: {}
    client: null
    Promise: Promise
    Events: null

  constructor: (options={}) ->
    parser.load options, @defaults, @
    @Redis ?= eval("require")("redis") # Obfuscated or else Webpack/Angular will try to inline the optional redis module. To override this behavior: pass the redis module to Bottleneck as the 'Redis' option.
    @Events ?= new Events @
    @terminated = false

    @client ?= @Redis.createClient @clientOptions
    @subscriber = @client.duplicate()
    @limiters = {}
    @shas = {}

    @ready = @Promise.all [@_setup(@client, false), @_setup(@subscriber, true)]
    .then => @_loadScripts()
    .then => { @client, @subscriber }

  _setup: (client, sub) ->
    client.setMaxListeners 0
    new @Promise (resolve, reject) =>
      client.on "error", (e) => @Events.trigger "error", e
      if sub
        client.on "message", (channel, message) =>
          @limiters[channel]?._store.onMessage channel, message
      if client.ready then resolve()
      else client.once "ready", resolve

  _loadScript: (name) ->
    new @Promise (resolve, reject) =>
      payload = Scripts.payload name
      @client.multi([["script", "load", payload]]).exec (err, replies) =>
        if err? then return reject err
        @shas[name] = replies[0]
        resolve replies[0]

  _loadScripts: -> @Promise.all(Scripts.names.map (k) => @_loadScript k)

  __runCommand__: (cmd) ->
    await @ready
    new @Promise (resolve, reject) =>
      @client.multi([cmd]).exec_atomic (err, replies) ->
        if err? then reject(err) else resolve(replies[0])

  __addLimiter__: (instance) ->
    @Promise.all [instance.channel(), instance.channel_client()].map (channel) =>
      new @Promise (resolve, reject) =>
        handler = (chan) =>
          if chan == channel
            @subscriber.removeListener "subscribe", handler
            @limiters[channel] = instance
            resolve()
        @subscriber.on "subscribe", handler
        @subscriber.subscribe channel

  __removeLimiter__: (instance) ->
    @Promise.all [instance.channel(), instance.channel_client()].map (channel) =>
      unless @terminated
        await new @Promise (resolve, reject) =>
          @subscriber.unsubscribe channel, (err, chan) ->
            if err? then return reject err
            if chan == channel then return resolve()
      delete @limiters[channel]

  __scriptArgs__: (name, id, args, cb) ->
    keys = Scripts.keys name, id
    [@shas[name], keys.length].concat keys, args, cb

  __scriptFn__: (name) ->
    @client.evalsha.bind(@client)

  disconnect: (flush=true) ->
    clearInterval(@limiters[k]._store.heartbeat) for k in Object.keys @limiters
    @limiters = {}
    @terminated = true

    @client.end flush
    @subscriber.end flush
    @Promise.resolve()

module.exports = RedisConnection
