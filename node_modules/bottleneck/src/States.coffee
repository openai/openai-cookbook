BottleneckError = require "./BottleneckError"
class States
  constructor: (@status) ->
    @_jobs = {}
    @counts = @status.map(-> 0)

  next: (id) ->
    current = @_jobs[id]
    next = current + 1
    if current? and next < @status.length
      @counts[current]--
      @counts[next]++
      @_jobs[id]++
    else if current?
      @counts[current]--
      delete @_jobs[id]

  start: (id) ->
    initial = 0
    @_jobs[id] = initial
    @counts[initial]++

  remove: (id) ->
    current = @_jobs[id]
    if current?
      @counts[current]--
      delete @_jobs[id]
    current?

  jobStatus: (id) -> @status[@_jobs[id]] ? null

  statusJobs: (status) ->
    if status?
      pos = @status.indexOf status
      if pos < 0
        throw new BottleneckError "status must be one of #{@status.join ', '}"
      k for k,v of @_jobs when v == pos
    else
      Object.keys @_jobs

  statusCounts: -> @counts.reduce(((acc, v, i) => acc[@status[i]] = v; acc), {})

module.exports = States
