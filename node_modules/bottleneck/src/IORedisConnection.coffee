parser = require "./parser"
Events = require "./Events"
Scripts = require "./Scripts"

class IORedisConnection
  datastore: "ioredis"
  defaults:
    Redis: null
    clientOptions: {}
    clusterNodes: null
    client: null
    Promise: Promise
    Events: null

  constructor: (options={}) ->
    parser.load options, @defaults, @
    @Redis ?= eval("require")("ioredis") # Obfuscated or else Webpack/Angular will try to inline the optional ioredis module. To override this behavior: pass the ioredis module to Bottleneck as the 'Redis' option.
    @Events ?= new Events @
    @terminated = false

    if @clusterNodes?
      @client = new @Redis.Cluster @clusterNodes, @clientOptions
      @subscriber = new @Redis.Cluster @clusterNodes, @clientOptions
    else if @client? and !@client.duplicate?
      @subscriber = new @Redis.Cluster @client.startupNodes, @client.options
    else
      @client ?= new @Redis @clientOptions
      @subscriber = @client.duplicate()
    @limiters = {}

    @ready = @Promise.all [@_setup(@client, false), @_setup(@subscriber, true)]
    .then =>
      @_loadScripts()
      { @client, @subscriber }

  _setup: (client, sub) ->
    client.setMaxListeners 0
    new @Promise (resolve, reject) =>
      client.on "error", (e) => @Events.trigger "error", e
      if sub
        client.on "message", (channel, message) =>
          @limiters[channel]?._store.onMessage channel, message
      if client.status == "ready" then resolve()
      else client.once "ready", resolve

  _loadScripts: -> Scripts.names.forEach (name) => @client.defineCommand name, { lua: Scripts.payload(name) }

  __runCommand__: (cmd) ->
    await @ready
    [[_, deleted]] = await @client.pipeline([cmd]).exec()
    deleted

  __addLimiter__: (instance) ->
    @Promise.all [instance.channel(), instance.channel_client()].map (channel) =>
      new @Promise (resolve, reject) =>
        @subscriber.subscribe channel, =>
          @limiters[channel] = instance
          resolve()

  __removeLimiter__: (instance) ->
    [instance.channel(), instance.channel_client()].forEach (channel) =>
      await @subscriber.unsubscribe channel unless @terminated
      delete @limiters[channel]

  __scriptArgs__: (name, id, args, cb) ->
    keys = Scripts.keys name, id
    [keys.length].concat keys, args, cb

  __scriptFn__: (name) ->
    @client[name].bind(@client)

  disconnect: (flush=true) ->
    clearInterval(@limiters[k]._store.heartbeat) for k in Object.keys @limiters
    @limiters = {}
    @terminated = true

    if flush
      @Promise.all [@client.quit(), @subscriber.quit()]
    else
      @client.disconnect()
      @subscriber.disconnect()
      @Promise.resolve()

module.exports = IORedisConnection
