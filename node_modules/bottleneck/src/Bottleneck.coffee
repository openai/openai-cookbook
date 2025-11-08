NUM_PRIORITIES = 10
DEFAULT_PRIORITY = 5

parser = require "./parser"
Queues = require "./Queues"
Job = require "./Job"
LocalDatastore = require "./LocalDatastore"
RedisDatastore = require "./RedisDatastore"
Events = require "./Events"
States = require "./States"
Sync = require "./Sync"

class Bottleneck
  Bottleneck.default = Bottleneck
  Bottleneck.Events = Events
  Bottleneck.version = Bottleneck::version = require("./version.json").version
  Bottleneck.strategy = Bottleneck::strategy = { LEAK:1, OVERFLOW:2, OVERFLOW_PRIORITY:4, BLOCK:3 }
  Bottleneck.BottleneckError = Bottleneck::BottleneckError = require "./BottleneckError"
  Bottleneck.Group = Bottleneck::Group = require "./Group"
  Bottleneck.RedisConnection = Bottleneck::RedisConnection = require "./RedisConnection"
  Bottleneck.IORedisConnection = Bottleneck::IORedisConnection = require "./IORedisConnection"
  Bottleneck.Batcher = Bottleneck::Batcher = require "./Batcher"
  jobDefaults:
    priority: DEFAULT_PRIORITY
    weight: 1
    expiration: null
    id: "<no-id>"
  storeDefaults:
    maxConcurrent: null
    minTime: 0
    highWater: null
    strategy: Bottleneck::strategy.LEAK
    penalty: null
    reservoir: null
    reservoirRefreshInterval: null
    reservoirRefreshAmount: null
    reservoirIncreaseInterval: null
    reservoirIncreaseAmount: null
    reservoirIncreaseMaximum: null
  localStoreDefaults:
    Promise: Promise
    timeout: null
    heartbeatInterval: 250
  redisStoreDefaults:
    Promise: Promise
    timeout: null
    heartbeatInterval: 5000
    clientTimeout: 10000
    Redis: null
    clientOptions: {}
    clusterNodes: null
    clearDatastore: false
    connection: null
  instanceDefaults:
    datastore: "local"
    connection: null
    id: "<no-id>"
    rejectOnDrop: true
    trackDoneStatus: false
    Promise: Promise
  stopDefaults:
    enqueueErrorMessage: "This limiter has been stopped and cannot accept new jobs."
    dropWaitingJobs: true
    dropErrorMessage: "This limiter has been stopped."

  constructor: (options={}, invalid...) ->
    @_validateOptions options, invalid
    parser.load options, @instanceDefaults, @
    @_queues = new Queues NUM_PRIORITIES
    @_scheduled = {}
    @_states = new States ["RECEIVED", "QUEUED", "RUNNING", "EXECUTING"].concat(if @trackDoneStatus then ["DONE"] else [])
    @_limiter = null
    @Events = new Events @
    @_submitLock = new Sync "submit", @Promise
    @_registerLock = new Sync "register", @Promise
    storeOptions = parser.load options, @storeDefaults, {}

    @_store = if @datastore == "redis" or @datastore == "ioredis" or @connection?
      storeInstanceOptions = parser.load options, @redisStoreDefaults, {}
      new RedisDatastore @, storeOptions, storeInstanceOptions
    else if @datastore == "local"
      storeInstanceOptions = parser.load options, @localStoreDefaults, {}
      new LocalDatastore @, storeOptions, storeInstanceOptions
    else
      throw new Bottleneck::BottleneckError "Invalid datastore type: #{@datastore}"

    @_queues.on "leftzero", => @_store.heartbeat?.ref?()
    @_queues.on "zero", => @_store.heartbeat?.unref?()

  _validateOptions: (options, invalid) ->
    unless options? and typeof options == "object" and invalid.length == 0
      throw new Bottleneck::BottleneckError "Bottleneck v2 takes a single object argument. Refer to https://github.com/SGrondin/bottleneck#upgrading-to-v2 if you're upgrading from Bottleneck v1."

  ready: -> @_store.ready

  clients: -> @_store.clients

  channel: -> "b_#{@id}"

  channel_client: -> "b_#{@id}_#{@_store.clientId}"

  publish: (message) -> @_store.__publish__ message

  disconnect: (flush=true) -> @_store.__disconnect__ flush

  chain: (@_limiter) -> @

  queued: (priority) -> @_queues.queued priority

  clusterQueued: -> @_store.__queued__()

  empty: -> @queued() == 0 and @_submitLock.isEmpty()

  running: -> @_store.__running__()

  done: -> @_store.__done__()

  jobStatus: (id) -> @_states.jobStatus id

  jobs: (status) -> @_states.statusJobs status

  counts: -> @_states.statusCounts()

  _randomIndex: -> Math.random().toString(36).slice(2)

  check: (weight=1) -> @_store.__check__ weight

  _clearGlobalState: (index) ->
    if @_scheduled[index]?
      clearTimeout @_scheduled[index].expiration
      delete @_scheduled[index]
      true
    else false

  _free: (index, job, options, eventInfo) ->
    try
      { running } = await @_store.__free__ index, options.weight
      @Events.trigger "debug", "Freed #{options.id}", eventInfo
      if running == 0 and @empty() then @Events.trigger "idle"
    catch e
      @Events.trigger "error", e

  _run: (index, job, wait) ->
    job.doRun()
    clearGlobalState = @_clearGlobalState.bind @, index
    run = @_run.bind @, index, job
    free = @_free.bind @, index, job

    @_scheduled[index] =
      timeout: setTimeout =>
        job.doExecute @_limiter, clearGlobalState, run, free
      , wait
      expiration: if job.options.expiration? then setTimeout ->
        job.doExpire clearGlobalState, run, free
      , wait + job.options.expiration
      job: job

  _drainOne: (capacity) ->
    @_registerLock.schedule =>
      if @queued() == 0 then return @Promise.resolve null
      queue = @_queues.getFirst()
      { options, args } = next = queue.first()
      if capacity? and options.weight > capacity then return @Promise.resolve null
      @Events.trigger "debug", "Draining #{options.id}", { args, options }
      index = @_randomIndex()
      @_store.__register__ index, options.weight, options.expiration
      .then ({ success, wait, reservoir }) =>
        @Events.trigger "debug", "Drained #{options.id}", { success, args, options }
        if success
          queue.shift()
          empty = @empty()
          if empty then @Events.trigger "empty"
          if reservoir == 0 then @Events.trigger "depleted", empty
          @_run index, next, wait
          @Promise.resolve options.weight
        else
          @Promise.resolve null

  _drainAll: (capacity, total=0) ->
    @_drainOne(capacity)
    .then (drained) =>
      if drained?
        newCapacity = if capacity? then capacity - drained else capacity
        @_drainAll(newCapacity, total + drained)
      else @Promise.resolve total
    .catch (e) => @Events.trigger "error", e

  _dropAllQueued: (message) -> @_queues.shiftAll (job) -> job.doDrop { message }

  stop: (options={}) ->
    options = parser.load options, @stopDefaults
    waitForExecuting = (at) =>
      finished = =>
        counts = @_states.counts
        (counts[0] + counts[1] + counts[2] + counts[3]) == at
      new @Promise (resolve, reject) =>
        if finished() then resolve()
        else
          @on "done", =>
            if finished()
              @removeAllListeners "done"
              resolve()
    done = if options.dropWaitingJobs
      @_run = (index, next) -> next.doDrop { message: options.dropErrorMessage }
      @_drainOne = => @Promise.resolve null
      @_registerLock.schedule => @_submitLock.schedule =>
        for k, v of @_scheduled
          if @jobStatus(v.job.options.id) == "RUNNING"
            clearTimeout v.timeout
            clearTimeout v.expiration
            v.job.doDrop { message: options.dropErrorMessage }
        @_dropAllQueued options.dropErrorMessage
        waitForExecuting(0)
    else
      @schedule { priority: NUM_PRIORITIES - 1, weight: 0 }, => waitForExecuting(1)
    @_receive = (job) -> job._reject new Bottleneck::BottleneckError options.enqueueErrorMessage
    @stop = => @Promise.reject new Bottleneck::BottleneckError "stop() has already been called"
    done

  _addToQueue: (job) =>
    { args, options } = job
    try
      { reachedHWM, blocked, strategy } = await @_store.__submit__ @queued(), options.weight
    catch error
      @Events.trigger "debug", "Could not queue #{options.id}", { args, options, error }
      job.doDrop { error }
      return false

    if blocked
      job.doDrop()
      return true
    else if reachedHWM
      shifted = if strategy == Bottleneck::strategy.LEAK then @_queues.shiftLastFrom(options.priority)
      else if strategy == Bottleneck::strategy.OVERFLOW_PRIORITY then @_queues.shiftLastFrom(options.priority + 1)
      else if strategy == Bottleneck::strategy.OVERFLOW then job
      if shifted? then shifted.doDrop()
      if not shifted? or strategy == Bottleneck::strategy.OVERFLOW
        if not shifted? then job.doDrop()
        return reachedHWM

    job.doQueue reachedHWM, blocked
    @_queues.push job
    await @_drainAll()
    reachedHWM

  _receive: (job) ->
    if @_states.jobStatus(job.options.id)?
      job._reject new Bottleneck::BottleneckError "A job with the same id already exists (id=#{job.options.id})"
      false
    else
      job.doReceive()
      @_submitLock.schedule @_addToQueue, job

  submit: (args...) ->
    if typeof args[0] == "function"
      [fn, args..., cb] = args
      options = parser.load {}, @jobDefaults
    else
      [options, fn, args..., cb] = args
      options = parser.load options, @jobDefaults

    task = (args...) =>
      new @Promise (resolve, reject) ->
        fn args..., (args...) ->
          (if args[0]? then reject else resolve) args

    job = new Job task, args, options, @jobDefaults, @rejectOnDrop, @Events, @_states, @Promise
    job.promise
    .then (args) -> cb? args...
    .catch (args) -> if Array.isArray args then cb? args... else cb? args
    @_receive job

  schedule: (args...) ->
    if typeof args[0] == "function"
      [task, args...] = args
      options = {}
    else
      [options, task, args...] = args
    job = new Job task, args, options, @jobDefaults, @rejectOnDrop, @Events, @_states, @Promise
    @_receive job
    job.promise

  wrap: (fn) ->
    schedule = @schedule.bind @
    wrapped = (args...) -> schedule fn.bind(@), args...
    wrapped.withOptions = (options, args...) -> schedule options, fn, args...
    wrapped

  updateSettings: (options={}) ->
    await @_store.__updateSettings__ parser.overwrite options, @storeDefaults
    parser.overwrite options, @instanceDefaults, @
    @

  currentReservoir: -> @_store.__currentReservoir__()

  incrementReservoir: (incr=0) -> @_store.__incrementReservoir__ incr

module.exports = Bottleneck
