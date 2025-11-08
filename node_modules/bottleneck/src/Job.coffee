NUM_PRIORITIES = 10
DEFAULT_PRIORITY = 5

parser = require "./parser"
BottleneckError = require "./BottleneckError"

class Job
  constructor: (@task, @args, options, jobDefaults, @rejectOnDrop, @Events, @_states, @Promise) ->
    @options = parser.load options, jobDefaults
    @options.priority = @_sanitizePriority @options.priority
    if @options.id == jobDefaults.id then @options.id = "#{@options.id}-#{@_randomIndex()}"
    @promise = new @Promise (@_resolve, @_reject) =>
    @retryCount = 0

  _sanitizePriority: (priority) ->
    sProperty = if ~~priority != priority then DEFAULT_PRIORITY else priority
    if sProperty < 0 then 0 else if sProperty > NUM_PRIORITIES-1 then NUM_PRIORITIES-1 else sProperty

  _randomIndex: -> Math.random().toString(36).slice(2)

  doDrop: ({ error, message="This job has been dropped by Bottleneck" } = {}) ->
    if @_states.remove @options.id
      if @rejectOnDrop then @_reject (error ? new BottleneckError message)
      @Events.trigger "dropped", { @args, @options, @task, @promise }
      true
    else
      false

  _assertStatus: (expected) ->
    status = @_states.jobStatus @options.id
    if not (status == expected or (expected == "DONE" and status == null))
      throw new BottleneckError "Invalid job status #{status}, expected #{expected}. Please open an issue at https://github.com/SGrondin/bottleneck/issues"

  doReceive: () ->
    @_states.start @options.id
    @Events.trigger "received", { @args, @options }

  doQueue: (reachedHWM, blocked) ->
    @_assertStatus "RECEIVED"
    @_states.next @options.id
    @Events.trigger "queued", { @args, @options, reachedHWM, blocked }

  doRun: () ->
    if @retryCount == 0
      @_assertStatus "QUEUED"
      @_states.next @options.id
    else @_assertStatus "EXECUTING"
    @Events.trigger "scheduled", { @args, @options }

  doExecute: (chained, clearGlobalState, run, free) ->
    if @retryCount == 0
      @_assertStatus "RUNNING"
      @_states.next @options.id
    else @_assertStatus "EXECUTING"
    eventInfo = { @args, @options, @retryCount }
    @Events.trigger "executing", eventInfo

    try
      passed = await if chained?
        chained.schedule @options, @task, @args...
      else @task @args...

      if clearGlobalState()
        @doDone eventInfo
        await free @options, eventInfo
        @_assertStatus "DONE"
        @_resolve passed
    catch error
      @_onFailure error, eventInfo, clearGlobalState, run, free

  doExpire: (clearGlobalState, run, free) ->
    if @_states.jobStatus @options.id == "RUNNING"
      @_states.next @options.id
    @_assertStatus "EXECUTING"
    eventInfo = { @args, @options, @retryCount }
    error = new BottleneckError "This job timed out after #{@options.expiration} ms."
    @_onFailure error, eventInfo, clearGlobalState, run, free

  _onFailure: (error, eventInfo, clearGlobalState, run, free) ->
    if clearGlobalState()
      retry = await @Events.trigger "failed", error, eventInfo
      if retry?
        retryAfter = ~~retry
        @Events.trigger "retry", "Retrying #{@options.id} after #{retryAfter} ms", eventInfo
        @retryCount++
        run retryAfter
      else
        @doDone eventInfo
        await free @options, eventInfo
        @_assertStatus "DONE"
        @_reject error

  doDone: (eventInfo) ->
    @_assertStatus "EXECUTING"
    @_states.next @options.id
    @Events.trigger "done", eventInfo

module.exports = Job
