var makeTest = require('./context')
var Bottleneck = require('./bottleneck')
var assert = require('assert')
var child_process = require('child_process')

describe('General', function () {
  var c

  afterEach(function () {
    return c.limiter.disconnect(false)
  })

  if (
    process.env.DATASTORE !== 'redis' && process.env.DATASTORE !== 'ioredis' &&
    process.env.BUILD !== 'es5' && process.env.BUILD !== 'light'
  ) {
    it('Should not leak memory on instantiation', async function () {
      c = makeTest()
      this.timeout(8000)
      const { iterate } = require('leakage')

      const result = await iterate.async(async () => {
        const limiter = new Bottleneck({ datastore: 'local' })
        await limiter.ready()
        return limiter.disconnect(false)
      }, { iterations: 25 })

    })

    it('Should not leak memory running jobs', async function () {
      c = makeTest()
      this.timeout(12000)
      const { iterate } = require('leakage')
      const limiter = new Bottleneck({ datastore: 'local', maxConcurrent: 1, minTime: 10 })
      await limiter.ready()
      var ctr = 0
      var i = 0

      const result = await iterate.async(async () => {
        await limiter.schedule(function (zero, one) {
          i = i + zero + one
        }, 0, 1)
        await limiter.schedule(function (zero, one) {
          i = i + zero + one
        }, 0, 1)
      }, { iterations: 25 })
      c.mustEqual(i, 302)
    })
  }

  it('Should prompt to upgrade', function () {
    c = makeTest()
    try {
      var limiter = new Bottleneck(1, 250)
    } catch (err) {
      c.mustEqual(err.message, 'Bottleneck v2 takes a single object argument. Refer to https://github.com/SGrondin/bottleneck#upgrading-to-v2 if you\'re upgrading from Bottleneck v1.')
    }
  })

  it('Should allow null capacity', function () {
    c = makeTest({ id: 'null', minTime: 0 })
    return c.limiter.updateSettings({ minTime: 10 })
  })

  it('Should keep scope', async function () {
    c = makeTest({ maxConcurrent: 1 })

    class Job {
      constructor() {
        this.value = 5
      }
      action(x) {
        return this.value + x
      }
    }
    var job = new Job()

    c.mustEqual(6, await c.limiter.schedule(() => job.action.bind(job)(1)))
    c.mustEqual(7, await c.limiter.wrap(job.action.bind(job))(2))
  })

  it('Should pass multiple arguments back even on errors when using submit()', function (done) {
    c = makeTest({ maxConcurrent: 1 })

    c.limiter.submit(c.job, new Error('welp'), 1, 2, function (err, x, y) {
      c.mustEqual(err.message, 'welp')
      c.mustEqual(x, 1)
      c.mustEqual(y, 2)
      done()
    })
  })

  it('Should expose the Events library', function (cb) {
    c = makeTest()

    class Hello {
      constructor() {
        this.emitter = new Bottleneck.Events(this)
      }

      doSomething() {
        this.emitter.trigger('info', 'hello', 'world', 123)
        return 5
      }
    }

    const myObject = new Hello();
    myObject.on('info', (...args) => {
      c.mustEqual(args, ['hello', 'world', 123])
      cb()
    })
    myObject.doSomething()
    c.mustEqual(myObject.emitter.listenerCount('info'), 1)
    c.mustEqual(myObject.emitter.listenerCount('nothing'), 0)

    myObject.on('blah', '')
    myObject.on('blah', null)
    myObject.on('blah')
    return myObject.emitter.trigger('blah')
  })

  describe('Counts and statuses', function () {
    it('Should check() and return the queued count with and without a priority value', async function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})

      c.mustEqual(await c.limiter.check(), true)

      c.mustEqual(c.limiter.queued(), 0)
      c.mustEqual(await c.limiter.clusterQueued(), 0)

      await c.limiter.submit({id: 1}, c.slowJob, 50, null, 1, c.noErrVal(1))
      c.mustEqual(c.limiter.queued(), 0) // It's already running

      c.mustEqual(await c.limiter.check(), false)

      await c.limiter.submit({id: 2}, c.slowJob, 50, null, 2, c.noErrVal(2))
      c.mustEqual(c.limiter.queued(), 1)
      c.mustEqual(await c.limiter.clusterQueued(), 1)
      c.mustEqual(c.limiter.queued(1), 0)
      c.mustEqual(c.limiter.queued(5), 1)

      await c.limiter.submit({id: 3}, c.slowJob, 50, null, 3, c.noErrVal(3))
      c.mustEqual(c.limiter.queued(), 2)
      c.mustEqual(await c.limiter.clusterQueued(), 2)
      c.mustEqual(c.limiter.queued(1), 0)
      c.mustEqual(c.limiter.queued(5), 2)

      await c.limiter.submit({id: 4}, c.slowJob, 50, null, 4, c.noErrVal(4))
      c.mustEqual(c.limiter.queued(), 3)
      c.mustEqual(await c.limiter.clusterQueued(), 3)
      c.mustEqual(c.limiter.queued(1), 0)
      c.mustEqual(c.limiter.queued(5), 3)

      await c.limiter.submit({priority: 1, id: 5}, c.job, null, 5, c.noErrVal(5))
      c.mustEqual(c.limiter.queued(), 4)
      c.mustEqual(await c.limiter.clusterQueued(), 4)
      c.mustEqual(c.limiter.queued(1), 1)
      c.mustEqual(c.limiter.queued(5), 3)

      var results = await c.last()
      c.mustEqual(c.limiter.queued(), 0)
      c.mustEqual(await c.limiter.clusterQueued(), 0)
      c.checkResultsOrder([[1], [5], [2], [3], [4]])
      c.checkDuration(450)
    })

    it('Should return the running and done counts', function () {
      c = makeTest({maxConcurrent: 5, minTime: 0})

      return Promise.all([c.limiter.running(), c.limiter.done()])
      .then(function ([running, done]) {
        c.mustEqual(running, 0)
        c.mustEqual(done, 0)
        c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 1 }, c.slowPromise, 100, null, 1), 1)
        c.pNoErrVal(c.limiter.schedule({ weight: 3, id: 2 }, c.slowPromise, 200, null, 2), 2)
        c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 3 }, c.slowPromise, 100, null, 3), 3)

        return c.limiter.schedule({ weight: 0, id: 4 }, c.promise, null)
      })
      .then(function () {
        return Promise.all([c.limiter.running(), c.limiter.done()])
      })
      .then(function ([running, done]) {
        c.mustEqual(running, 5)
        c.mustEqual(done, 0)
        return c.wait(125)
      })
      .then(function () {
        return Promise.all([c.limiter.running(), c.limiter.done()])
      })
      .then(function ([running, done]) {
        c.mustEqual(running, 3)
        c.mustEqual(done, 2)
        return c.wait(100)
      })
      .then(function () {
        return Promise.all([c.limiter.running(), c.limiter.done()])
      })
      .then(function ([running, done]) {
        c.mustEqual(running, 0)
        c.mustEqual(done, 5)
        return c.last()
      })
      .then(function (results) {
        c.checkDuration(200)
        c.checkResultsOrder([[], [1], [3], [2]])
      })
    })

    it('Should refuse duplicate Job IDs', async function () {
      c = makeTest({maxConcurrent: 2, minTime: 100, trackDoneStatus: true})

      try {
        await c.limiter.schedule({ id: 'a' }, c.promise, null, 1)
        await c.limiter.schedule({ id: 'b' }, c.promise, null, 2)
        await c.limiter.schedule({ id: 'a' }, c.promise, null, 3)
      } catch (e) {
        c.mustEqual(e.message, 'A job with the same id already exists (id=a)')
      }
    })

    it('Should return job statuses', function () {
      c = makeTest({maxConcurrent: 2, minTime: 100})

      c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0 })

      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 1 }, c.slowPromise, 100, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 2 }, c.slowPromise, 200, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule({ weight: 2, id: 3 }, c.slowPromise, 100, null, 3), 3)
      c.mustEqual(c.limiter.counts(), { RECEIVED: 3, QUEUED: 0, RUNNING: 0, EXECUTING: 0 })

      return c.wait(50)
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 1, EXECUTING: 1 })
        c.mustEqual(c.limiter.jobStatus(1), 'EXECUTING')
        c.mustEqual(c.limiter.jobStatus(2), 'RUNNING')
        c.mustEqual(c.limiter.jobStatus(3), 'QUEUED')

        return c.last()
      })
      .then(function (results) {
        c.checkDuration(400)
        c.checkResultsOrder([[1], [2], [3]])
      })
    })

    it('Should return job statuses, including DONE', function () {
      c = makeTest({maxConcurrent: 2, minTime: 100, trackDoneStatus: true})

      c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 0 })

      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 1 }, c.slowPromise, 100, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 2 }, c.slowPromise, 200, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule({ weight: 2, id: 3 }, c.slowPromise, 100, null, 3), 3)
      c.mustEqual(c.limiter.counts(), { RECEIVED: 3, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 0 })

      return c.wait(50)
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 1, EXECUTING: 1, DONE: 0 })
        c.mustEqual(c.limiter.jobStatus(1), 'EXECUTING')
        c.mustEqual(c.limiter.jobStatus(2), 'RUNNING')
        c.mustEqual(c.limiter.jobStatus(3), 'QUEUED')

        return c.wait(100)
      })
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 0, EXECUTING: 1, DONE: 1 })
        c.mustEqual(c.limiter.jobStatus(1), 'DONE')
        c.mustEqual(c.limiter.jobStatus(2), 'EXECUTING')
        c.mustEqual(c.limiter.jobStatus(3), 'QUEUED')

        return c.last()
      })
      .then(function (results) {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 4 })
        c.checkDuration(400)
        c.checkResultsOrder([[1], [2], [3]])
      })
    })

    it('Should return jobs for a status', function () {
      c = makeTest({maxConcurrent: 2, minTime: 100, trackDoneStatus: true})

      c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 0 })

      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 1 }, c.slowPromise, 100, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 2 }, c.slowPromise, 200, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule({ weight: 2, id: 3 }, c.slowPromise, 100, null, 3), 3)
      c.mustEqual(c.limiter.counts(), { RECEIVED: 3, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 0 })

      c.mustEqual(c.limiter.jobs(), ['1', '2', '3'])
      c.mustEqual(c.limiter.jobs('RECEIVED'), ['1', '2', '3'])

      return c.wait(50)
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 1, EXECUTING: 1, DONE: 0 })
        c.mustEqual(c.limiter.jobs('EXECUTING'), ['1'])
        c.mustEqual(c.limiter.jobs('RUNNING'), ['2'])
        c.mustEqual(c.limiter.jobs('QUEUED'), ['3'])

        return c.wait(100)
      })
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 0, EXECUTING: 1, DONE: 1 })
        c.mustEqual(c.limiter.jobs('DONE'), ['1'])
        c.mustEqual(c.limiter.jobs('EXECUTING'), ['2'])
        c.mustEqual(c.limiter.jobs('QUEUED'), ['3'])

        return c.last()
      })
      .then(function (results) {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 4 })
        c.checkDuration(400)
        c.checkResultsOrder([[1], [2], [3]])
      })
    })

    it('Should trigger events on status changes', function () {
      c = makeTest({maxConcurrent: 2, minTime: 100, trackDoneStatus: true})
      var onReceived = 0
      var onQueued = 0
      var onScheduled = 0
      var onExecuting = 0
      var onDone = 0
      c.limiter.on('received', (info) => {
        c.mustEqual(Object.keys(info).sort(), ['args', 'options'])
        onReceived++
      })
      c.limiter.on('queued', (info) => {
        c.mustEqual(Object.keys(info).sort(), ['args', 'blocked', 'options', 'reachedHWM'])
        onQueued++
      })
      c.limiter.on('scheduled', (info) => {
        c.mustEqual(Object.keys(info).sort(), ['args', 'options'])
        onScheduled++
      })
      c.limiter.on('executing', (info) => {
        c.mustEqual(Object.keys(info).sort(), ['args', 'options', 'retryCount'])
        onExecuting++
      })
      c.limiter.on('done', (info) => {
        c.mustEqual(Object.keys(info).sort(), ['args', 'options', 'retryCount'])
        onDone++
      })

      c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 0 })

      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 1 }, c.slowPromise, 100, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 2 }, c.slowPromise, 200, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule({ weight: 2, id: 3 }, c.slowPromise, 100, null, 3), 3)
      c.mustEqual(c.limiter.counts(), { RECEIVED: 3, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 0 })

      c.mustEqual([onReceived, onQueued, onScheduled, onExecuting, onDone], [3, 0, 0, 0, 0])

      return c.wait(50)
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 1, EXECUTING: 1, DONE: 0 })
        c.mustEqual([onReceived, onQueued, onScheduled, onExecuting, onDone], [3, 3, 2, 1, 0])

        return c.wait(100)
      })
      .then(function () {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 1, RUNNING: 0, EXECUTING: 1, DONE: 1 })
        c.mustEqual(c.limiter.jobs('DONE'), ['1'])
        c.mustEqual(c.limiter.jobs('EXECUTING'), ['2'])
        c.mustEqual(c.limiter.jobs('QUEUED'), ['3'])
        c.mustEqual([onReceived, onQueued, onScheduled, onExecuting, onDone], [3, 3, 2, 2, 1])

        return c.last()
      })
      .then(function (results) {
        c.mustEqual(c.limiter.counts(), { RECEIVED: 0, QUEUED: 0, RUNNING: 0, EXECUTING: 0, DONE: 4 })
        c.mustEqual([onReceived, onQueued, onScheduled, onExecuting, onDone], [4, 4, 4, 4, 4])
        c.checkDuration(400)
        c.checkResultsOrder([[1], [2], [3]])
      })
    })
  })

  describe('Events', function () {
    it('Should return itself', function () {
      c = makeTest({ id: 'test-limiter' })

      var returned = c.limiter.on('ready', function () { })
      c.mustEqual(returned.id, 'test-limiter')
    })

    it('Should fire events on empty queue', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})
      var calledEmpty = 0
      var calledIdle = 0
      var calledDepleted = 0

      c.limiter.on('empty', function () { calledEmpty++ })
      c.limiter.on('idle', function () { calledIdle++ })
      c.limiter.on('depleted', function () { calledDepleted++ })

      return c.pNoErrVal(c.limiter.schedule({id: 1}, c.slowPromise, 50, null, 1), 1)
      .then(function () {
        c.mustEqual(calledEmpty, 1)
        c.mustEqual(calledIdle, 1)
        return Promise.all([
          c.pNoErrVal(c.limiter.schedule({id: 2}, c.slowPromise, 50, null, 2), 2),
          c.pNoErrVal(c.limiter.schedule({id: 3}, c.slowPromise, 50, null, 3), 3)
        ])
      })
      .then(function () {
        return c.limiter.submit({id: 4}, c.slowJob, 50, null, 4, null)
      })
      .then(function () {
        c.checkDuration(250)
        c.checkResultsOrder([[1], [2], [3]])
        c.mustEqual(calledEmpty, 3)
        c.mustEqual(calledIdle, 2)
        c.mustEqual(calledDepleted, 0)
        return c.last()
      })
    })

    it('Should fire events once', function () {
      c = makeTest({maxConcurrent: 1, minTime: 100})
      var calledEmptyOnce = 0
      var calledIdleOnce = 0
      var calledEmpty = 0
      var calledIdle = 0
      var calledDepleted = 0

      c.limiter.once('empty', function () { calledEmptyOnce++ })
      c.limiter.once('idle', function () { calledIdleOnce++ })
      c.limiter.on('empty', function () { calledEmpty++ })
      c.limiter.on('idle', function () { calledIdle++ })
      c.limiter.on('depleted', function () { calledDepleted++ })

      c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 1), 1)

      return c.pNoErrVal(c.limiter.schedule(c.promise, null, 2), 2)
      .then(function () {
        c.mustEqual(calledEmptyOnce, 1)
        c.mustEqual(calledIdleOnce, 1)
        c.mustEqual(calledEmpty, 1)
        c.mustEqual(calledIdle, 1)
        return c.pNoErrVal(c.limiter.schedule(c.promise, null, 3), 3)
      })
      .then(function () {
        c.checkDuration(200)
        c.checkResultsOrder([[1], [2], [3]])
        c.mustEqual(calledEmptyOnce, 1)
        c.mustEqual(calledIdleOnce, 1)
        c.mustEqual(calledEmpty, 2)
        c.mustEqual(calledIdle, 2)
        c.mustEqual(calledDepleted, 0)
      })
    })

    it('Should support faulty event listeners', function (done) {
      c = makeTest({maxConcurrent: 1, minTime: 100, errorEventsExpected: true})
      var calledError = 0

      c.limiter.on('error', function (err) {
        calledError++
        if (err.message === 'Oh noes!' && calledError === 1) {
          done()
        }
      })
      c.limiter.on('empty', function () {
        throw new Error('Oh noes!')
      })

      c.pNoErrVal(c.limiter.schedule(c.promise, null, 1), 1)
    })

    it('Should wait for async event listeners', function (done) {
      c = makeTest({maxConcurrent: 1, minTime: 100, errorEventsExpected: true})
      var calledError = 0

      c.limiter.on('error', function (err) {
        calledError++
        if (err.message === 'It broke!' && calledError === 1) {
          done()
        }
      })
      c.limiter.on('empty', function () {
        return c.slowPromise(100, null, 1, 2)
        .then(function (x) {
          c.mustEqual(x, [1, 2])
          return Promise.reject(new Error('It broke!'))
        })
      })

      c.pNoErrVal(c.limiter.schedule(c.promise, null, 1), 1)
    })
  })

  describe('High water limit', function () {
    it('Should support highWater set to 0', function () {
      c = makeTest({maxConcurrent: 1, minTime: 0, highWater: 0, rejectOnDrop: false})

      var first = c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 3), 3)
      c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 4), 4)

      return first
      .then(function () {
        return c.last({ weight: 0 })
      })
      .then(function (results) {
        c.checkDuration(50)
        c.checkResultsOrder([[1]])
      })
    })

    it('Should support highWater set to 1', function () {
      c = makeTest({maxConcurrent: 1, minTime: 0, highWater: 1, rejectOnDrop: false})

      var first = c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 3), 3)
      var last = c.pNoErrVal(c.limiter.schedule(c.slowPromise, 50, null, 4), 4)

      return Promise.all([first, last])
      .then(function () {
        return c.last({ weight: 0 })
      })
      .then(function (results) {
        c.checkDuration(100)
        c.checkResultsOrder([[1], [4]])
      })
    })
  })

  describe('Weight', function () {
    it('Should not add jobs with a weight above the maxConcurrent', function () {
      c = makeTest({maxConcurrent: 2})

      c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.promise, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule({ weight: 2 }, c.promise, null, 2), 2)

      return c.limiter.schedule({ weight: 3 }, c.promise, null, 3)
      .catch(function (err) {
        c.mustEqual(err.message, 'Impossible to add a job having a weight of 3 to a limiter having a maxConcurrent setting of 2')
        return c.last()
      })
      .then(function (results) {
        c.checkDuration(0)
        c.checkResultsOrder([[1], [2]])
      })
    })


    it('Should support custom job weights', function () {
      c = makeTest({maxConcurrent: 2})

      c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.slowPromise, 100, null, 1), 1)
      c.pNoErrVal(c.limiter.schedule({ weight: 2 }, c.slowPromise, 200, null, 2), 2)
      c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.slowPromise, 100, null, 3), 3)
      c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.slowPromise, 100, null, 4), 4)
      c.pNoErrVal(c.limiter.schedule({ weight: 0 }, c.slowPromise, 100, null, 5), 5)

      return c.last()
      .then(function (results) {
        c.checkDuration(400)
        c.checkResultsOrder([[1], [2], [3], [4], [5]])
      })
    })

    it('Should overflow at the correct rate', function () {
      c = makeTest({
        maxConcurrent: 2,
        reservoir: 3
      })

      var calledDepleted = 0
      var emptyArguments = []
      c.limiter.on('depleted', function (empty) {
        emptyArguments.push(empty)
        calledDepleted++
      })

      var p1 = c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 1 }, c.slowPromise, 100, null, 1), 1)
      var p2 = c.pNoErrVal(c.limiter.schedule({ weight: 2, id: 2 }, c.slowPromise, 150, null, 2), 2)
      var p3 = c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 3 }, c.slowPromise, 100, null, 3), 3)
      var p4 = c.pNoErrVal(c.limiter.schedule({ weight: 1, id: 4 }, c.slowPromise, 100, null, 4), 4)

      return Promise.all([p1, p2])
      .then(function () {
        c.mustEqual(c.limiter.queued(), 2)
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        c.mustEqual(calledDepleted, 1)
        return c.limiter.incrementReservoir(1)
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 1)
        return c.last({ priority: 1, weight: 0 })
      })
      .then(function (results) {
        c.mustEqual(calledDepleted, 3)
        c.mustEqual(c.limiter.queued(), 1)
        c.checkDuration(250)
        c.checkResultsOrder([[1], [2]])
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        return c.limiter.updateSettings({ reservoir: 1 })
      })
      .then(function () {
        return Promise.all([p3, p4])
      })
      .then(function () {
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        c.mustEqual(calledDepleted, 4)
        c.mustEqual(emptyArguments, [false, false, false, true])
      })
    })
  })

  describe('Expiration', function () {
    it('Should cancel jobs', function () {
      c = makeTest({ maxConcurrent: 2 })
      var t0 = Date.now()

      return Promise.all([
        c.pNoErrVal(c.limiter.schedule({ id: 'very-slow-no-expiration' }, c.slowPromise, 150, null, 1), 1),

        c.limiter.schedule({ expiration: 50, id: 'slow-with-expiration' }, c.slowPromise, 75, null, 2)
        .then(function () {
          return Promise.reject(new Error("Should have timed out."))
        })
        .catch(function (err) {
          c.mustEqual(err.message, 'This job timed out after 50 ms.')
          var duration = Date.now() - t0
          assert(duration > 45 && duration < 80)

          return Promise.all([c.limiter.running(), c.limiter.done()])
        })
        .then(function ([running, done]) {
          c.mustEqual(running, 1)
          c.mustEqual(done, 1)
        })

      ])
      .then(function () {
        var duration = Date.now() - t0
        assert(duration > 145 && duration < 180)
        return Promise.all([c.limiter.running(), c.limiter.done()])
      })
      .then(function ([running, done]) {
        c.mustEqual(running, 0)
        c.mustEqual(done, 2)
      })
    })
  })

  describe('Pubsub', function () {
    it('Should pass strings', function (done) {
      c = makeTest({ maxConcurrent: 2 })

      c.limiter.on('message', function (msg) {
        c.mustEqual(msg, 'hello')
        done()
      })

      c.limiter.publish('hello')
    })

    it('Should pass objects', function (done) {
      c = makeTest({ maxConcurrent: 2 })
      var obj = {
        array: ['abc', true],
        num: 235.59
      }

      c.limiter.on('message', function (msg) {
        c.mustEqual(JSON.parse(msg), obj)
        done()
      })

      c.limiter.publish(JSON.stringify(obj))
    })
  })

  describe('Reservoir Refresh', function () {
    it('Should auto-refresh the reservoir', function () {
      c = makeTest({
        reservoir: 8,
        reservoirRefreshInterval: 150,
        reservoirRefreshAmount: 5,
        heartbeatInterval: 75 // not for production use
      })
      var calledDepleted = 0

      c.limiter.on('depleted', function () {
        calledDepleted++
      })

      return Promise.all([
        c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.promise, null, 1), 1),
        c.pNoErrVal(c.limiter.schedule({ weight: 2 }, c.promise, null, 2), 2),
        c.pNoErrVal(c.limiter.schedule({ weight: 3 }, c.promise, null, 3), 3),
        c.pNoErrVal(c.limiter.schedule({ weight: 4 }, c.promise, null, 4), 4),
        c.pNoErrVal(c.limiter.schedule({ weight: 5 }, c.promise, null, 5), 5)
      ])
      .then(function () {
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        return c.last({ weight: 0, priority: 9 })
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3], [4], [5]])
        c.mustEqual(calledDepleted, 2)
        c.checkDuration(300)
      })
    })

    it('Should allow staggered X by Y type usage', function () {
      c = makeTest({
        reservoir: 2,
        reservoirRefreshInterval: 150,
        reservoirRefreshAmount: 2,
        heartbeatInterval: 75 // not for production use
      })

      return Promise.all([
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 1), 1),
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 2), 2),
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 3), 3),
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 4), 4)
      ])
      .then(function () {
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        return c.last({ weight: 0, priority: 9 })
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3], [4]])
        c.checkDuration(150)
      })
    })

    it('Should keep process alive until queue is empty', function (done) {
      c = makeTest()
      var options = {
        cwd: process.cwd() + '/test/spawn',
        timeout: 1000
      }
      child_process.exec('node refreshKeepAlive.js', options, function (err, stdout, stderr) {
        c.mustEqual(stdout, '[0][0][2][2]')
        c.mustEqual(stderr, '')
        done(err)
      })
    })

  })

  describe('Reservoir Increase', function () {
    it('Should auto-increase the reservoir', async function () {
      c = makeTest({
        reservoir: 3,
        reservoirIncreaseInterval: 150,
        reservoirIncreaseAmount: 5,
        heartbeatInterval: 75 // not for production use
      })
      var calledDepleted = 0

      c.limiter.on('depleted', function () {
        calledDepleted++
      })

      await Promise.all([
        c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.promise, null, 1), 1),
        c.pNoErrVal(c.limiter.schedule({ weight: 2 }, c.promise, null, 2), 2),
        c.pNoErrVal(c.limiter.schedule({ weight: 3 }, c.promise, null, 3), 3),
        c.pNoErrVal(c.limiter.schedule({ weight: 4 }, c.promise, null, 4), 4),
        c.pNoErrVal(c.limiter.schedule({ weight: 5 }, c.promise, null, 5), 5)
      ])
      const reservoir = await c.limiter.currentReservoir()
      c.mustEqual(reservoir, 3)

      const results = await c.last({ weight: 0, priority: 9 })
      c.checkResultsOrder([[1], [2], [3], [4], [5]])
      c.mustEqual(calledDepleted, 1)
      c.checkDuration(450)
    })

    it('Should auto-increase the reservoir up to a maximum', async function () {
      c = makeTest({
        reservoir: 3,
        reservoirIncreaseInterval: 150,
        reservoirIncreaseAmount: 5,
        reservoirIncreaseMaximum: 6,
        heartbeatInterval: 75 // not for production use
      })
      var calledDepleted = 0

      c.limiter.on('depleted', function () {
        calledDepleted++
      })

      await Promise.all([
        c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.promise, null, 1), 1),
        c.pNoErrVal(c.limiter.schedule({ weight: 2 }, c.promise, null, 2), 2),
        c.pNoErrVal(c.limiter.schedule({ weight: 3 }, c.promise, null, 3), 3),
        c.pNoErrVal(c.limiter.schedule({ weight: 4 }, c.promise, null, 4), 4),
        c.pNoErrVal(c.limiter.schedule({ weight: 5 }, c.promise, null, 5), 5)
      ])
      const reservoir = await c.limiter.currentReservoir()
      c.mustEqual(reservoir, 1)

      const results = await c.last({ weight: 0, priority: 9 })
      c.checkResultsOrder([[1], [2], [3], [4], [5]])
      c.mustEqual(calledDepleted, 1)
      c.checkDuration(450)
    })

    it('Should allow staggered X by Y type usage', function () {
      c = makeTest({
        reservoir: 2,
        reservoirIncreaseInterval: 150,
        reservoirIncreaseAmount: 2,
        heartbeatInterval: 75 // not for production use
      })

      return Promise.all([
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 1), 1),
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 2), 2),
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 3), 3),
        c.pNoErrVal(c.limiter.schedule(c.promise, null, 4), 4)
      ])
      .then(function () {
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        return c.last({ weight: 0, priority: 9 })
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3], [4]])
        c.checkDuration(150)
      })
    })

    it('Should keep process alive until queue is empty', function (done) {
      c = makeTest()
      var options = {
        cwd: process.cwd() + '/test/spawn',
        timeout: 1000
      }
      child_process.exec('node increaseKeepAlive.js', options, function (err, stdout, stderr) {
        c.mustEqual(stdout, '[0][0][2][2]')
        c.mustEqual(stderr, '')
        done(err)
      })
    })
  })

})
