class DLList
  constructor: (@incr, @decr) ->
    @_first = null
    @_last = null
    @length = 0
  push: (value) ->
    @length++
    @incr?()
    node = { value, prev: @_last, next: null }
    if @_last?
      @_last.next = node
      @_last = node
    else @_first = @_last = node
    undefined
  shift: () ->
    if not @_first? then return
    else
      @length--
      @decr?()
    value = @_first.value
    if (@_first = @_first.next)?
      @_first.prev = null
    else
      @_last = null
    value
  first: () -> if @_first? then @_first.value
  getArray: () ->
    node = @_first
    while node? then (ref = node; node = node.next; ref.value)
  forEachShift: (cb) ->
    node = @shift()
    while node? then (cb node; node = @shift())
    undefined
  debug: () ->
    node = @_first
    while node? then (ref = node; node = node.next; { value: ref.value, prev: ref.prev?.value, next: ref.next?.value })

module.exports = DLList
