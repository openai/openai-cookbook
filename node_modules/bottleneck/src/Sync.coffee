DLList = require "./DLList"
class Sync
  constructor: (@name, @Promise) ->
    @_running = 0
    @_queue = new DLList()
  isEmpty: -> @_queue.length == 0
  _tryToRun: ->
    if (@_running < 1) and @_queue.length > 0
      @_running++
      { task, args, resolve, reject } = @_queue.shift()
      cb = try
        returned = await task args...
        () -> resolve returned
      catch error
        () -> reject error
      @_running--
      @_tryToRun()
      cb()
  schedule: (task, args...) =>
    resolve = reject = null
    promise = new @Promise (_resolve, _reject) ->
      resolve = _resolve
      reject = _reject
    @_queue.push { task, args, resolve, reject }
    @_tryToRun()
    promise

module.exports = Sync
