var makeTest = require('./context')
var Bottleneck = require('./bottleneck')
var assert = require('assert')

describe('Promises', function () {
  var c

  afterEach(function () {
    return c.limiter.disconnect(false)
  })

  it('Should support promises', function () {
    c = makeTest({maxConcurrent: 1, minTime: 100})

    c.limiter.submit(c.job, null, 1, 9, c.noErrVal(1, 9))
    c.limiter.submit(c.job, null, 2, c.noErrVal(2))
    c.limiter.submit(c.job, null, 3, c.noErrVal(3))
    c.pNoErrVal(c.limiter.schedule(c.promise, null, 4, 5), 4, 5)

    return c.last()
    .then(function (results) {
      c.checkResultsOrder([[1,9], [2], [3], [4,5]])
      c.checkDuration(300)
    })
  })

  it('Should pass error on failure', function () {
    var failureMessage = 'failed'
    c = makeTest({maxConcurrent: 1, minTime: 100})

    return c.limiter.schedule(c.promise, new Error(failureMessage))
    .catch(function (err) {
      c.mustEqual(err.message, failureMessage)
    })
  })

  it('Should allow non-Promise returns', function () {
    c = makeTest()
    var str = 'This is a string'

    return c.limiter.schedule(() => str)
    .then(function (x) {
      c.mustEqual(x, str)
    })
  })

  it('Should get rejected when rejectOnDrop is true', function () {
    c = makeTest({
      maxConcurrent: 1,
      minTime: 0,
      highWater: 1,
      strategy: Bottleneck.strategy.OVERFLOW,
      rejectOnDrop: true
    })
    var dropped = 0
    var caught = 0
    var p1
    var p2

    c.limiter.on('dropped', function () {
      dropped++
    })

    p1 = c.pNoErrVal(c.limiter.schedule({id: 1}, c.slowPromise, 50, null, 1), 1)
    p2 = c.pNoErrVal(c.limiter.schedule({id: 2}, c.slowPromise, 50, null, 2), 2)

    return c.limiter.schedule({id: 3}, c.slowPromise, 50, null, 3)
    .catch(function (err) {
      c.mustEqual(err.message, 'This job has been dropped by Bottleneck')
      assert(err instanceof Bottleneck.BottleneckError)
      caught++
      return Promise.all([p1, p2])
    })
    .then(c.last)
    .then(function (results) {
      c.checkResultsOrder([[1], [2]])
      c.checkDuration(100)
      c.mustEqual(dropped, 1)
      c.mustEqual(caught, 1)
    })
  })

  it('Should automatically wrap an exception in a rejected promise - schedule()', function () {
    c = makeTest({maxConcurrent: 1, minTime: 100})

    return c.limiter.schedule(() => {
      throw new Error('I will reject')
    })
    .then(() => assert(false))
    .catch(err => {
      assert(err.message === 'I will reject');
    })
  })

  describe('Wrap', function () {
    it('Should wrap', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})

      c.limiter.submit(c.job, null, 1, c.noErrVal(1))
      c.limiter.submit(c.job, null, 2, c.noErrVal(2))
      c.limiter.submit(c.job, null, 3, c.noErrVal(3))

      var wrapped = c.limiter.wrap(c.promise)
      c.pNoErrVal(wrapped(null, 4), 4)

      return c.last()
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3], [4]])
        c.checkDuration(300)
      })
    })

    it('Should automatically wrap a returned value in a resolved promise', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})

      fn = c.limiter.wrap(() => { return 7 });

      return fn().then(result => {
        assert(result === 7);
      })
    })

    it('Should automatically wrap an exception in a rejected promise', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})

      fn = c.limiter.wrap(() => { throw new Error('I will reject') });

      return fn().then(() => assert(false)).catch(error => {
        assert(error.message === 'I will reject');
      })
    })

    it('Should inherit the original target for wrapped methods', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})

      var object = {
        fn: c.limiter.wrap(function () { return this })
      }

      return object.fn().then(result => {
        assert(result === object)
      })
    })

    it('Should inherit the original target on prototype methods', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})

      class Animal {
        constructor(name) { this.name = name }
        getName() { return this.name }
      }

      Animal.prototype.getName = c.limiter.wrap(Animal.prototype.getName)
      let elephant = new Animal('Dumbo')

      return elephant.getName().then(result => {
        assert(result === 'Dumbo')
      })
    })

    it('Should pass errors back', function () {
      var failureMessage = 'BLEW UP!!!'
      c = makeTest({maxConcurrent: 1, minTime: 100})

      var wrapped = c.limiter.wrap(c.promise)
      c.pNoErrVal(wrapped(null, 1), 1)
      c.pNoErrVal(wrapped(null, 2), 2)

      return wrapped(new Error(failureMessage), 3)
      .catch(function (err) {
        c.mustEqual(err.message, failureMessage)
        return c.last()
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3]])
        c.checkDuration(200)
      })
    })

    it('Should allow passing options', function () {
      var failureMessage = 'BLEW UP!!!'
      c = makeTest({maxConcurrent: 1, minTime: 50})

      var wrapped = c.limiter.wrap(c.promise)
      c.pNoErrVal(wrapped(null, 1), 1)
      c.pNoErrVal(wrapped(null, 2), 2)
      c.pNoErrVal(wrapped(null, 3), 3)
      c.pNoErrVal(wrapped(null, 4), 4)
      c.pNoErrVal(wrapped.withOptions({ priority: 1 }, null, 5), 5)

      return wrapped.withOptions({ priority: 1 }, new Error(failureMessage), 6)
      .catch(function (err) {
        c.mustEqual(err.message, failureMessage)
        return c.last()
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [5], [6], [3], [4]])
        c.checkDuration(250)
      })
    })
  })
})
