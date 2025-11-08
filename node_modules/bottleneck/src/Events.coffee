class Events
  constructor: (@instance) ->
    @_events = {}
    if @instance.on? or @instance.once? or @instance.removeAllListeners?
      throw new Error "An Emitter already exists for this object"
    @instance.on = (name, cb) => @_addListener name, "many", cb
    @instance.once = (name, cb) => @_addListener name, "once", cb
    @instance.removeAllListeners = (name=null) =>
      if name? then delete @_events[name] else @_events = {}
  _addListener: (name, status, cb) ->
    @_events[name] ?= []
    @_events[name].push {cb, status}
    @instance
  listenerCount: (name) ->
    if @_events[name]? then @_events[name].length else 0
  trigger: (name, args...) ->
    try
      if name != "debug" then @trigger "debug", "Event triggered: #{name}", args
      return unless @_events[name]?
      @_events[name] = @_events[name].filter (listener) -> listener.status != "none"
      promises = @_events[name].map (listener) =>
        return if listener.status == "none"
        if listener.status == "once" then listener.status = "none"
        try
          returned = listener.cb?(args...)
          if typeof returned?.then == "function"
            await returned
          else
            returned
        catch e
          if "name" != "error" then @trigger "error", e
          null
      (await Promise.all promises).find (x) -> x?
    catch e
      if "name" != "error" then @trigger "error", e
      null

module.exports = Events
