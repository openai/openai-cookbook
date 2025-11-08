var makeTest = require('./context')
var Bottleneck = require('./bottleneck')
var assert = require('assert')
var child_process = require('child_process')

describe('Retries', function () {
  var c

  afterEach(function () {
    return c.limiter.disconnect(false)
  })

  it('Should retry when requested by the user (sync)', async function () {
    c = makeTest({ trackDoneStatus: true })
    var failedEvents = 0
    var retryEvents = 0

    c.limiter.on('failed', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      c.mustEqual(info.retryCount, failedEvents)
      failedEvents++
      return 50
    })

    c.limiter.on('retry', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      retryEvents++
    })

    var times = 0
    const job = function () {
      times++
      if (times <= 2) {
        return Promise.reject(new Error('boom'))
      }
      return Promise.resolve('Success!')
    }

    c.mustEqual(await c.limiter.schedule(job), 'Success!')
    const results = await c.results()
    assert(results.elapsed > 90 && results.elapsed < 130)
    c.mustEqual(failedEvents, 2)
    c.mustEqual(retryEvents, 2)
    c.mustEqual(c.limiter.counts().EXECUTING, 0)
    c.mustEqual(c.limiter.counts().DONE, 1)
  })

  it('Should retry when requested by the user (async)', async function () {
    c = makeTest({ trackDoneStatus: true })
    var failedEvents = 0
    var retryEvents = 0

    c.limiter.on('failed', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      c.mustEqual(info.retryCount, failedEvents)
      failedEvents++
      return Promise.resolve(50)
    })

    c.limiter.on('retry', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      retryEvents++
    })

    var times = 0
    const job = function () {
      times++
      if (times <= 2) {
        return Promise.reject(new Error('boom'))
      }
      return Promise.resolve('Success!')
    }

    c.mustEqual(await c.limiter.schedule(job), 'Success!')
    const results = await c.results()
    assert(results.elapsed > 90 && results.elapsed < 130)
    c.mustEqual(failedEvents, 2)
    c.mustEqual(retryEvents, 2)
    c.mustEqual(c.limiter.counts().EXECUTING, 0)
    c.mustEqual(c.limiter.counts().DONE, 1)
  })

  it('Should not retry when user returns an error (sync)', async function () {
    c = makeTest({ errorEventsExpected: true, trackDoneStatus: true })
    var failedEvents = 0
    var retryEvents = 0
    var errorEvents = 0
    var caught = false

    c.limiter.on('failed', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      c.mustEqual(info.retryCount, failedEvents)
      failedEvents++
      throw new Error('Nope')
    })

    c.limiter.on('retry', function (error, info) {
      retryEvents++
    })

    c.limiter.on('error', function (error, info) {
      c.mustEqual(error.message, 'Nope')
      errorEvents++
    })

    const job = function () {
      return Promise.reject(new Error('boom'))
    }

    try {
      await c.limiter.schedule(job)
      throw new Error('Should not reach')
    } catch (error) {
      c.mustEqual(error.message, 'boom')
      caught = true
    }
    c.mustEqual(failedEvents, 1)
    c.mustEqual(retryEvents, 0)
    c.mustEqual(errorEvents, 1)
    c.mustEqual(caught, true)
    c.mustEqual(c.limiter.counts().EXECUTING, 0)
    c.mustEqual(c.limiter.counts().DONE, 1)
  })

  it('Should not retry when user returns an error (async)', async function () {
    c = makeTest({ errorEventsExpected: true, trackDoneStatus: true })
    var failedEvents = 0
    var retryEvents = 0
    var errorEvents = 0
    var caught = false

    c.limiter.on('failed', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      c.mustEqual(info.retryCount, failedEvents)
      failedEvents++
      return Promise.reject(new Error('Nope'))
    })

    c.limiter.on('retry', function (error, info) {
      retryEvents++
    })

    c.limiter.on('error', function (error, info) {
      c.mustEqual(error.message, 'Nope')
      errorEvents++
    })

    const job = function () {
      return Promise.reject(new Error('boom'))
    }

    try {
      await c.limiter.schedule(job)
      throw new Error('Should not reach')
    } catch (error) {
      c.mustEqual(error.message, 'boom')
      caught = true
    }
    c.mustEqual(failedEvents, 1)
    c.mustEqual(retryEvents, 0)
    c.mustEqual(errorEvents, 1)
    c.mustEqual(caught, true)
    c.mustEqual(c.limiter.counts().EXECUTING, 0)
    c.mustEqual(c.limiter.counts().DONE, 1)
  })

  it('Should not retry when user returns null (sync)', async function () {
    c = makeTest({ trackDoneStatus: true })
    var failedEvents = 0
    var retryEvents = 0
    var caught = false

    c.limiter.on('failed', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      c.mustEqual(info.retryCount, failedEvents)
      failedEvents++
      return null
    })

    c.limiter.on('retry', function (error, info) {
      retryEvents++
    })

    const job = function () {
      return Promise.reject(new Error('boom'))
    }

    try {
      await c.limiter.schedule(job)
      throw new Error('Should not reach')
    } catch (error) {
      c.mustEqual(error.message, 'boom')
      caught = true
    }
    c.mustEqual(failedEvents, 1)
    c.mustEqual(retryEvents, 0)
    c.mustEqual(caught, true)
    c.mustEqual(c.limiter.counts().EXECUTING, 0)
    c.mustEqual(c.limiter.counts().DONE, 1)
  })

  it('Should not retry when user returns null (async)', async function () {
    c = makeTest({ trackDoneStatus: true })
    var failedEvents = 0
    var retryEvents = 0
    var caught = false

    c.limiter.on('failed', function (error, info) {
      c.mustEqual(c.limiter.counts().EXECUTING, 1)
      c.mustEqual(info.retryCount, failedEvents)
      failedEvents++
      return Promise.resolve(null)
    })

    c.limiter.on('retry', function (error, info) {
      retryEvents++
    })

    const job = function () {
      return Promise.reject(new Error('boom'))
    }

    try {
      await c.limiter.schedule(job)
      throw new Error('Should not reach')
    } catch (error) {
      c.mustEqual(error.message, 'boom')
      caught = true
    }
    c.mustEqual(failedEvents, 1)
    c.mustEqual(retryEvents, 0)
    c.mustEqual(caught, true)
    c.mustEqual(c.limiter.counts().EXECUTING, 0)
    c.mustEqual(c.limiter.counts().DONE, 1)
  })

})
