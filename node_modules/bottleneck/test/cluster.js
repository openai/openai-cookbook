var makeTest = require('./context')
var Bottleneck = require('./bottleneck')
var Scripts = require('../lib/Scripts.js')
var assert = require('assert')
var packagejson = require('../package.json')

if (process.env.DATASTORE === 'redis' || process.env.DATASTORE === 'ioredis') {

  var limiterKeys = function (limiter) {
    return Scripts.allKeys(limiter._store.originalId)
  }
  var countKeys = function (limiter) {
    return runCommand(limiter, 'exists', limiterKeys(limiter))
  }
  var deleteKeys = function (limiter) {
    return runCommand(limiter, 'del', limiterKeys(limiter))
  }
  var runCommand = function (limiter, command, args) {
    return new Promise(function (resolve, reject) {
      limiter._store.clients.client[command](...args, function (err, data) {
        if (err != null) return reject(err)
        return resolve(data)
      })
    })
  }

  describe('Cluster-only', function () {
    var c

    afterEach(function () {
      return c.limiter.disconnect(false)
    })

    it('Should return a promise for ready()', function () {
      c = makeTest({ maxConcurrent: 2 })

      return c.limiter.ready()
    })

    it('Should return clients', function () {
      c = makeTest({ maxConcurrent: 2 })

      return c.limiter.ready()
      .then(function (clients) {
        c.mustEqual(Object.keys(clients), ['client', 'subscriber'])
        c.mustEqual(Object.keys(c.limiter.clients()), ['client', 'subscriber'])
      })
    })

    it('Should return a promise when disconnecting', function () {
      c = makeTest({ maxConcurrent: 2 })

      return c.limiter.disconnect()
      .then(function () {
        // do nothing
      })
    })

    it('Should allow passing a limiter\'s connection to a new limiter', function () {
      c = makeTest()
      c.limiter.connection.id = 'some-id'
      var limiter = new Bottleneck({
        minTime: 50,
        connection: c.limiter.connection
      })

      return Promise.all([c.limiter.ready(), limiter.ready()])
      .then(function () {
        c.mustEqual(limiter.connection.id, 'some-id')
        c.mustEqual(limiter.datastore, process.env.DATASTORE)

        return Promise.all([
          c.pNoErrVal(c.limiter.schedule(c.promise, null, 1), 1),
          c.pNoErrVal(limiter.schedule(c.promise, null, 2), 2)
        ])
      })
      .then(c.last)
      .then(function (results) {
        c.checkResultsOrder([[1], [2]])
        c.checkDuration(0)
      })
    })

    it('Should allow passing a limiter\'s connection to a new Group', function () {
      c = makeTest()
      c.limiter.connection.id = 'some-id'
      var group = new Bottleneck.Group({
        minTime: 50,
        connection: c.limiter.connection
      })
      var limiter1 = group.key('A')
      var limiter2 = group.key('B')

      return Promise.all([c.limiter.ready(), limiter1.ready(), limiter2.ready()])
      .then(function () {
        c.mustEqual(limiter1.connection.id, 'some-id')
        c.mustEqual(limiter2.connection.id, 'some-id')
        c.mustEqual(limiter1.datastore, process.env.DATASTORE)
        c.mustEqual(limiter2.datastore, process.env.DATASTORE)

        return Promise.all([
          c.pNoErrVal(c.limiter.schedule(c.promise, null, 1), 1),
          c.pNoErrVal(limiter1.schedule(c.promise, null, 2), 2),
          c.pNoErrVal(limiter2.schedule(c.promise, null, 3), 3)
        ])
      })
      .then(c.last)
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3]])
        c.checkDuration(0)
      })
    })

    it('Should allow passing a Group\'s connection to a new limiter', function () {
      c = makeTest()
      var group = new Bottleneck.Group({
        minTime: 50,
        datastore: process.env.DATASTORE,
        clearDatastore: true
      })
      group.connection.id = 'some-id'

      var limiter1 = group.key('A')
      var limiter2 = new Bottleneck({
        minTime: 50,
        connection: group.connection
      })

      return Promise.all([limiter1.ready(), limiter2.ready()])
      .then(function () {
        c.mustEqual(limiter1.connection.id, 'some-id')
        c.mustEqual(limiter2.connection.id, 'some-id')
        c.mustEqual(limiter1.datastore, process.env.DATASTORE)
        c.mustEqual(limiter2.datastore, process.env.DATASTORE)

        return Promise.all([
          c.pNoErrVal(limiter1.schedule(c.promise, null, 1), 1),
          c.pNoErrVal(limiter2.schedule(c.promise, null, 2), 2)
        ])
      })
      .then(c.last)
      .then(function (results) {
        c.checkResultsOrder([[1], [2]])
        c.checkDuration(0)
        return group.disconnect()
      })
    })

    it('Should allow passing a Group\'s connection to a new Group', function () {
      c = makeTest()
      var group1 = new Bottleneck.Group({
        minTime: 50,
        datastore: process.env.DATASTORE,
        clearDatastore: true
      })
      group1.connection.id = 'some-id'

      var group2 = new Bottleneck.Group({
        minTime: 50,
        connection: group1.connection,
        clearDatastore: true
      })

      var limiter1 = group1.key('AAA')
      var limiter2 = group1.key('BBB')
      var limiter3 = group1.key('CCC')
      var limiter4 = group1.key('DDD')

      return Promise.all([
        limiter1.ready(),
        limiter2.ready(),
        limiter3.ready(),
        limiter4.ready()
      ])
      .then(function () {
        c.mustEqual(group1.connection.id, 'some-id')
        c.mustEqual(group2.connection.id, 'some-id')
        c.mustEqual(limiter1.connection.id, 'some-id')
        c.mustEqual(limiter2.connection.id, 'some-id')
        c.mustEqual(limiter3.connection.id, 'some-id')
        c.mustEqual(limiter4.connection.id, 'some-id')
        c.mustEqual(limiter1.datastore, process.env.DATASTORE)
        c.mustEqual(limiter2.datastore, process.env.DATASTORE)
        c.mustEqual(limiter3.datastore, process.env.DATASTORE)
        c.mustEqual(limiter4.datastore, process.env.DATASTORE)

        return Promise.all([
          c.pNoErrVal(limiter1.schedule(c.promise, null, 1), 1),
          c.pNoErrVal(limiter2.schedule(c.promise, null, 2), 2),
          c.pNoErrVal(limiter3.schedule(c.promise, null, 3), 3),
          c.pNoErrVal(limiter4.schedule(c.promise, null, 4), 4)
        ])
      })
      .then(c.last)
      .then(function (results) {
        c.checkResultsOrder([[1], [2], [3], [4]])
        c.checkDuration(0)
        return group1.disconnect()
      })
    })

    it('Should not have a key TTL by default for standalone limiters', function () {
      c = makeTest()

      return c.limiter.ready()
      .then(function () {
        var settings_key = limiterKeys(c.limiter)[0]
        return runCommand(c.limiter, 'ttl', [settings_key])
      })
      .then(function (ttl) {
        assert(ttl < 0)
      })
    })

    it('Should allow timeout setting for standalone limiters', function () {
      c = makeTest({ timeout: 5 * 60 * 1000 })

      return c.limiter.ready()
      .then(function () {
        var settings_key = limiterKeys(c.limiter)[0]
        return runCommand(c.limiter, 'ttl', [settings_key])
      })
      .then(function (ttl) {
        assert(ttl >= 290 && ttl <= 305)
      })
    })

    it('Should compute reservoir increased based on number of missed intervals', async function () {
      const settings = {
        id: 'missed-intervals',
        clearDatastore: false,
        reservoir: 2,
        reservoirIncreaseInterval: 100,
        reservoirIncreaseAmount: 2,
        timeout: 2000
      }
      c = makeTest({ ...settings })
      await c.limiter.ready()

      c.mustEqual(await c.limiter.currentReservoir(), 2)

      const settings_key = limiterKeys(c.limiter)[0]
      await runCommand(c.limiter, 'hincrby', [settings_key, 'lastReservoirIncrease', -3000])

      const limiter2 = new Bottleneck({ ...settings, datastore: process.env.DATASTORE })
      await limiter2.ready()

      c.mustEqual(await c.limiter.currentReservoir(), 62) // 2 + ((3000 / 100) * 2) === 62

      await limiter2.disconnect()
    })

    it('Should migrate from 2.8.0', function () {
      c = makeTest({ id: 'migrate' })
      var settings_key = limiterKeys(c.limiter)[0]
      var limiter2

      return c.limiter.ready()
      .then(function () {
        var settings_key = limiterKeys(c.limiter)[0]
        return Promise.all([
          runCommand(c.limiter, 'hset', [settings_key, 'version', '2.8.0']),
          runCommand(c.limiter, 'hdel', [settings_key, 'done', 'capacityPriorityCounter', 'clientTimeout']),
          runCommand(c.limiter, 'hset', [settings_key, 'lastReservoirRefresh', ''])
        ])
      })
      .then(function () {
        limiter2 = new Bottleneck({
          id: 'migrate',
          datastore: process.env.DATASTORE
        })
        return limiter2.ready()
      })
      .then(function () {
        return runCommand(c.limiter, 'hmget', [
          settings_key,
          'version',
          'done',
          'reservoirRefreshInterval',
          'reservoirRefreshAmount',
          'capacityPriorityCounter',
          'clientTimeout',
          'reservoirIncreaseAmount',
          'reservoirIncreaseMaximum',
          // Add new values here, before these 2 timestamps
          'lastReservoirRefresh',
          'lastReservoirIncrease'
        ])
      })
      .then(function (values) {
        var timestamps = values.slice(-2)
        timestamps.forEach((t) => assert(parseInt(t) > Date.now() - 500))
        c.mustEqual(values.slice(0, -timestamps.length), [
          '2.18.0',
          '0',
          '',
          '',
          '0',
          '10000',
          '',
          ''
         ])
      })
      .then(function () {
        return limiter2.disconnect(false)
      })
    })

    it('Should keep track of each client\'s queue length', async function () {
      c = makeTest({
        id: 'queues',
        maxConcurrent: 1,
        trackDoneStatus: true
      })
      var limiter2 = new Bottleneck({
        datastore: process.env.DATASTORE,
        id: 'queues',
        maxConcurrent: 1,
        trackDoneStatus: true
      })
      var client_num_queued_key = limiterKeys(c.limiter)[5]
      var clientId1 = c.limiter._store.clientId
      var clientId2 = limiter2._store.clientId

      await c.limiter.ready()
      await limiter2.ready()

      var p0 = c.limiter.schedule({id: 0}, c.slowPromise, 100, null, 0)
      await c.limiter._submitLock.schedule(() => Promise.resolve())

      var p1 = c.limiter.schedule({id: 1}, c.promise, null, 1)
      var p2 = c.limiter.schedule({id: 2}, c.promise, null, 2)
      var p3 = limiter2.schedule({id: 3}, c.promise, null, 3)

      await Promise.all([
        c.limiter._submitLock.schedule(() => Promise.resolve()),
        limiter2._submitLock.schedule(() => Promise.resolve())
      ])

      var queuedA = await runCommand(c.limiter, 'hgetall', [client_num_queued_key])
      c.mustEqual(c.limiter.counts().QUEUED, 2)
      c.mustEqual(limiter2.counts().QUEUED, 1)
      c.mustEqual(~~queuedA[clientId1], 2)
      c.mustEqual(~~queuedA[clientId2], 1)

      c.mustEqual(await c.limiter.clusterQueued(), 3)

      await Promise.all([p0, p1, p2, p3])
      var queuedB = await runCommand(c.limiter, 'hgetall', [client_num_queued_key])
      c.mustEqual(c.limiter.counts().QUEUED, 0)
      c.mustEqual(limiter2.counts().QUEUED, 0)
      c.mustEqual(~~queuedB[clientId1], 0)
      c.mustEqual(~~queuedB[clientId2], 0)
      c.mustEqual(c.limiter.counts().DONE, 3)
      c.mustEqual(limiter2.counts().DONE, 1)

      c.mustEqual(await c.limiter.clusterQueued(), 0)

      return limiter2.disconnect(false)
    })

    it('Should publish capacity increases', function () {
      c = makeTest({ maxConcurrent: 2 })
      var limiter2
      var p3, p4

      return c.limiter.ready()
      .then(function () {
        limiter2 = new Bottleneck({ datastore: process.env.DATASTORE })
        return limiter2.ready()
      })
      .then(function () {
        var p1 = c.limiter.schedule({id: 1}, c.slowPromise, 100, null, 1)
        var p2 = c.limiter.schedule({id: 2}, c.slowPromise, 100, null, 2)

        return c.limiter.schedule({id: 0, weight: 0}, c.promise, null, 0)
      })
      .then(function () {
        return limiter2.schedule({id: 3}, c.slowPromise, 100, null, 3)
      })
      .then(c.last)
      .then(function (results) {
        c.checkResultsOrder([[0], [1], [2], [3]])
        c.checkDuration(200)

        return limiter2.disconnect(false)
      })
    })

    it('Should publish capacity changes on reservoir changes', function () {
      c = makeTest({
        maxConcurrent: 2,
        reservoir: 2
      })
      var limiter2
      var p3, p4

      return c.limiter.ready()
      .then(function () {
        limiter2 = new Bottleneck({
          datastore: process.env.DATASTORE,
        })
        return limiter2.ready()
      })
      .then(function () {
        var p1 = c.limiter.schedule({id: 1}, c.slowPromise, 100, null, 1)
        var p2 = c.limiter.schedule({id: 2}, c.slowPromise, 100, null, 2)

        return c.limiter.schedule({id: 0, weight: 0}, c.promise, null, 0)
      })
      .then(function () {
        p3 = limiter2.schedule({id: 3, weight: 2}, c.slowPromise, 100, null, 3)
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        return c.limiter.updateSettings({ reservoir: 1 })
      })
      .then(function () {
        return c.limiter.incrementReservoir(1)
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 2)
        return p3
      })
      .then(function (result) {
        c.mustEqual(result, [3])
        return c.limiter.currentReservoir()
      })
      .then(function (reservoir) {
        c.mustEqual(reservoir, 0)
        return c.last({ weight: 0 })
      })
      .then(function (results) {
        c.checkResultsOrder([[0], [1], [2], [3]])
        c.checkDuration(210)
      })
      .then(function (data) {
        return limiter2.disconnect(false)
      })
    })

    it('Should remove track job data and remove lost jobs', function () {
      c = makeTest({
        id: 'lost',
        errorEventsExpected: true
      })
      var clientId = c.limiter._store.clientId
      var limiter1 = new Bottleneck({ datastore: process.env.DATASTORE })
      var limiter2 = new Bottleneck({
          id: 'lost',
          datastore: process.env.DATASTORE,
          heartbeatInterval: 150
        })
      var getData = function (limiter) {
        c.mustEqual(limiterKeys(limiter).length, 8) // Asserting, to remember to edit this test when keys change
        var [
          settings_key,
          job_weights_key,
          job_expirations_key,
          job_clients_key,
          client_running_key,
          client_num_queued_key,
          client_last_registered_key,
          client_last_seen_key
        ] = limiterKeys(limiter)

        return Promise.all([
          runCommand(limiter1, 'hmget', [settings_key, 'running', 'done']),
          runCommand(limiter1, 'hgetall', [job_weights_key]),
          runCommand(limiter1, 'zcard', [job_expirations_key]),
          runCommand(limiter1, 'hvals', [job_clients_key]),
          runCommand(limiter1, 'zrange', [client_running_key, '0', '-1', 'withscores']),
          runCommand(limiter1, 'hvals', [client_num_queued_key]),
          runCommand(limiter1, 'zrange', [client_last_registered_key, '0', '-1', 'withscores']),
          runCommand(limiter1, 'zrange', [client_last_seen_key, '0', '-1', 'withscores'])
        ])
      }
      var sumWeights = function (weights) {
        return Object.keys(weights).reduce((acc, x) => {
          return acc + ~~weights[x]
        }, 0)
      }
      var numExpirations = 0
      var errorHandler = function (err) {
        if (err.message.indexOf('This job timed out') === 0) {
          numExpirations++
        }
      }

      return Promise.all([c.limiter.ready(), limiter1.ready(), limiter2.ready()])
      .then(function () {
        // No expiration, it should not be removed
        c.pNoErrVal(c.limiter.schedule({ weight: 1 }, c.slowPromise, 150, null, 1), 1),

        // Expiration present, these jobs should be removed automatically
        c.limiter.schedule({ expiration: 50, weight: 2 }, c.slowPromise, 75, null, 2).catch(errorHandler)
        c.limiter.schedule({ expiration: 50, weight: 3 }, c.slowPromise, 75, null, 3).catch(errorHandler)
        c.limiter.schedule({ expiration: 50, weight: 4 }, c.slowPromise, 75, null, 4).catch(errorHandler)
        c.limiter.schedule({ expiration: 50, weight: 5 }, c.slowPromise, 75, null, 5).catch(errorHandler)

        return c.limiter._submitLock.schedule(() => Promise.resolve(true))
      })
      .then(function () {
        return c.limiter._drainAll()
      })
      .then(function () {
        return c.limiter.disconnect(false)
      })
      .then(function () {
      })
      .then(function () {
        return getData(c.limiter)
      })
      .then(function ([
          settings,
          job_weights,
          job_expirations,
          job_clients,
          client_running,
          client_num_queued,
          client_last_registered,
          client_last_seen
      ]) {
        c.mustEqual(settings, ['15', '0'])
        c.mustEqual(sumWeights(job_weights), 15)
        c.mustEqual(job_expirations, 4)
        c.mustEqual(job_clients.length, 5)
        job_clients.forEach((id) => c.mustEqual(id, clientId))
        c.mustEqual(sumWeights(client_running), 15)
        c.mustEqual(client_num_queued, ['0', '0'])
        c.mustEqual(client_last_registered[1], '0')
        assert(client_last_seen[1] > Date.now() - 1000)
        var passed = Date.now() - parseFloat(client_last_registered[3])
        assert(passed > 0 && passed < 20)

        return c.wait(170)
      })
      .then(function () {
        return getData(c.limiter)
      })
      .then(function ([
        settings,
        job_weights,
        job_expirations,
        job_clients,
        client_running,
        client_num_queued,
        client_last_registered,
        client_last_seen
      ]) {
        c.mustEqual(settings, ['1', '14'])
        c.mustEqual(sumWeights(job_weights), 1)
        c.mustEqual(job_expirations, 0)
        c.mustEqual(job_clients.length, 1)
        job_clients.forEach((id) => c.mustEqual(id, clientId))
        c.mustEqual(sumWeights(client_running), 1)
        c.mustEqual(client_num_queued, ['0', '0'])
        c.mustEqual(client_last_registered[1], '0')
        assert(client_last_seen[1] > Date.now() - 1000)
        var passed = Date.now() - parseFloat(client_last_registered[3])
        assert(passed > 170 && passed < 200)

        c.mustEqual(numExpirations, 4)
      })
      .then(function () {
        return Promise.all([
          limiter1.disconnect(false),
          limiter2.disconnect(false)
        ])
      })
    })

    it('Should clear unresponsive clients', async function () {
      c = makeTest({
        id: 'unresponsive',
        maxConcurrent: 1,
        timeout: 1000,
        clientTimeout: 100,
        heartbeat: 50
      })
      const limiter2 = new Bottleneck({
        id: 'unresponsive',
        datastore: process.env.DATASTORE
      })

      await Promise.all([c.limiter.running(), limiter2.running()])

      const client_running_key = limiterKeys(limiter2)[4]
      const client_num_queued_key = limiterKeys(limiter2)[5]
      const client_last_registered_key = limiterKeys(limiter2)[6]
      const client_last_seen_key = limiterKeys(limiter2)[7]
      const numClients = () => Promise.all([
        runCommand(c.limiter, 'zcard', [client_running_key]),
        runCommand(c.limiter, 'hlen', [client_num_queued_key]),
        runCommand(c.limiter, 'zcard', [client_last_registered_key]),
        runCommand(c.limiter, 'zcard', [client_last_seen_key])
      ])

      c.mustEqual(await numClients(), [2, 2, 2, 2])

      await limiter2.disconnect(false)
      await c.wait(150)

      await c.limiter.running()

      c.mustEqual(await numClients(), [1, 1, 1, 1])

    })


    it('Should not clear unresponsive clients with unexpired running jobs', async function () {
      c = makeTest({
        id: 'unresponsive-unexpired',
        maxConcurrent: 1,
        timeout: 1000,
        clientTimeout: 200,
        heartbeat: 2000
      })
      const limiter2 = new Bottleneck({
        id: 'unresponsive-unexpired',
        datastore: process.env.DATASTORE
      })

      await c.limiter.ready()
      await limiter2.ready()

      const client_running_key = limiterKeys(limiter2)[4]
      const client_num_queued_key = limiterKeys(limiter2)[5]
      const client_last_registered_key = limiterKeys(limiter2)[6]
      const client_last_seen_key = limiterKeys(limiter2)[7]
      const numClients = () => Promise.all([
        runCommand(limiter2, 'zcard', [client_running_key]),
        runCommand(limiter2, 'hlen', [client_num_queued_key]),
        runCommand(limiter2, 'zcard', [client_last_registered_key]),
        runCommand(limiter2, 'zcard', [client_last_seen_key])
      ])

      const job = c.limiter.schedule(c.slowPromise, 500, null, 1)

      await c.wait(300)

      // running() triggers process_tick and that will attempt to remove client 1
      // but it shouldn't do it because it has a running job
      c.mustEqual(await limiter2.running(), 1)

      c.mustEqual(await numClients(), [2, 2, 2, 2])

      await job

      c.mustEqual(await limiter2.running(), 0)

      await limiter2.disconnect(false)
    })

    it('Should clear unresponsive clients after last jobs are expired', async function () {
      c = makeTest({
        id: 'unresponsive-expired',
        maxConcurrent: 1,
        timeout: 1000,
        clientTimeout: 200,
        heartbeat: 2000
      })
      const limiter2 = new Bottleneck({
        id: 'unresponsive-expired',
        datastore: process.env.DATASTORE
      })

      await c.limiter.ready()
      await limiter2.ready()

      const client_running_key = limiterKeys(limiter2)[4]
      const client_num_queued_key = limiterKeys(limiter2)[5]
      const client_last_registered_key = limiterKeys(limiter2)[6]
      const client_last_seen_key = limiterKeys(limiter2)[7]
      const numClients = () => Promise.all([
        runCommand(limiter2, 'zcard', [client_running_key]),
        runCommand(limiter2, 'hlen', [client_num_queued_key]),
        runCommand(limiter2, 'zcard', [client_last_registered_key]),
        runCommand(limiter2, 'zcard', [client_last_seen_key])
      ])

      const job = c.limiter.schedule({ expiration: 250 }, c.slowPromise, 300, null, 1)
      await c.wait(100) // wait for it to register

      c.mustEqual(await c.limiter.running(), 1)
      c.mustEqual(await numClients(), [2,2,2,2])

      let dropped = false
      try {
        await job
      } catch (e) {
        if (e.message === 'This job timed out after 250 ms.') {
          dropped = true
        } else {
          throw e
        }
      }
      assert(dropped)

      await c.wait(200)

      c.mustEqual(await limiter2.running(), 0)
      c.mustEqual(await numClients(), [1,1,1,1])

      await limiter2.disconnect(false)
    })

    it('Should use shared settings', function () {
      c = makeTest({ maxConcurrent: 2 })
      var limiter2 = new Bottleneck({ maxConcurrent: 1, datastore: process.env.DATASTORE })

      return Promise.all([
        limiter2.schedule(c.slowPromise, 100, null, 1),
        limiter2.schedule(c.slowPromise, 100, null, 2)
      ])
      .then(function () {
        return limiter2.disconnect(false)
      })
      .then(function () {
        return c.last()
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2]])
        c.checkDuration(100)
      })
    })

    it('Should clear previous settings', function () {
      c = makeTest({ maxConcurrent: 2 })
      var limiter2

      return c.limiter.ready()
      .then(function () {
        limiter2 = new Bottleneck({ maxConcurrent: 1, datastore: process.env.DATASTORE, clearDatastore: true })
        return limiter2.ready()
      })
      .then(function () {
        return Promise.all([
          c.limiter.schedule(c.slowPromise, 100, null, 1),
          c.limiter.schedule(c.slowPromise, 100, null, 2)
        ])
      })
      .then(function () {
        return limiter2.disconnect(false)
      })
      .then(function () {
        return c.last()
      })
      .then(function (results) {
        c.checkResultsOrder([[1], [2]])
        c.checkDuration(200)
      })
    })

    it('Should safely handle connection failures', function () {
      c = makeTest({
        clientOptions: { port: 1 },
        errorEventsExpected: true
      })

      return new Promise(function (resolve, reject) {
        c.limiter.on('error', function (err) {
          assert(err != null)
          resolve()
        })

        c.limiter.ready()
        .then(function () {
          reject(new Error('Should not have connected'))
        })
        .catch(function (err) {
          reject(err)
        })
      })
    })

    it('Should chain local and distributed limiters (total concurrency)', function () {
      c = makeTest({ id: 'limiter1', maxConcurrent: 3 })
      var limiter2 = new Bottleneck({ id: 'limiter2', maxConcurrent: 1 })
      var limiter3 = new Bottleneck({ id: 'limiter3', maxConcurrent: 2 })

      limiter2.on('error', (err) => console.log(err))

      limiter2.chain(c.limiter)
      limiter3.chain(c.limiter)

      return Promise.all([
        limiter2.schedule(c.slowPromise, 100, null, 1),
        limiter2.schedule(c.slowPromise, 100, null, 2),
        limiter2.schedule(c.slowPromise, 100, null, 3),
        limiter3.schedule(c.slowPromise, 100, null, 4),
        limiter3.schedule(c.slowPromise, 100, null, 5),
        limiter3.schedule(c.slowPromise, 100, null, 6)
      ])
      .then(c.last)
      .then(function (results) {
        c.checkDuration(300)
        c.checkResultsOrder([[1], [4], [5], [2], [6], [3]])

        assert(results.calls[0].time >= 100 && results.calls[0].time < 200)
        assert(results.calls[1].time >= 100 && results.calls[1].time < 200)
        assert(results.calls[2].time >= 100 && results.calls[2].time < 200)

        assert(results.calls[3].time >= 200 && results.calls[3].time < 300)
        assert(results.calls[4].time >= 200 && results.calls[4].time < 300)

        assert(results.calls[5].time >= 300 && results.calls[2].time < 400)
      })
    })

    it('Should chain local and distributed limiters (partial concurrency)', function () {
      c = makeTest({ maxConcurrent: 2 })
      var limiter2 = new Bottleneck({ maxConcurrent: 1 })
      var limiter3 = new Bottleneck({ maxConcurrent: 2 })

      limiter2.chain(c.limiter)
      limiter3.chain(c.limiter)

      return Promise.all([
        limiter2.schedule(c.slowPromise, 100, null, 1),
        limiter2.schedule(c.slowPromise, 100, null, 2),
        limiter2.schedule(c.slowPromise, 100, null, 3),
        limiter3.schedule(c.slowPromise, 100, null, 4),
        limiter3.schedule(c.slowPromise, 100, null, 5),
        limiter3.schedule(c.slowPromise, 100, null, 6)
      ])
      .then(c.last)
      .then(function (results) {
        c.checkDuration(300)
        c.checkResultsOrder([[1], [4], [5], [2], [6], [3]])

        assert(results.calls[0].time >= 100 && results.calls[0].time < 200)
        assert(results.calls[1].time >= 100 && results.calls[1].time < 200)

        assert(results.calls[2].time >= 200 && results.calls[2].time < 300)
        assert(results.calls[3].time >= 200 && results.calls[3].time < 300)

        assert(results.calls[4].time >= 300 && results.calls[4].time < 400)
        assert(results.calls[5].time >= 300 && results.calls[2].time < 400)
      })
    })

    it('Should use the limiter ID to build Redis keys', function () {
      c = makeTest()
      var randomId = c.limiter._randomIndex()
      var limiter = new Bottleneck({ id: randomId, datastore: process.env.DATASTORE, clearDatastore: true })

      return limiter.ready()
      .then(function () {
        var keys = limiterKeys(limiter)
        keys.forEach((key) => assert(key.indexOf(randomId) > 0))
        return deleteKeys(limiter)
      })
      .then(function (deleted) {
        c.mustEqual(deleted, 5)
        return limiter.disconnect(false)
      })
    })

    it('Should not fail when Redis data is missing', function () {
      c = makeTest()
      var limiter = new Bottleneck({ datastore: process.env.DATASTORE, clearDatastore: true })

      return limiter.running()
      .then(function (running) {
        c.mustEqual(running, 0)
        return deleteKeys(limiter)
      })
      .then(function (deleted) {
        c.mustEqual(deleted, 5)
        return countKeys(limiter)
      })
      .then(function (count) {
        c.mustEqual(count, 0)
        return limiter.running()
      })
      .then(function (running) {
        c.mustEqual(running, 0)
        return countKeys(limiter)
      })
      .then(function (count) {
        assert(count > 0)
        return limiter.disconnect(false)
      })
    })

    it('Should drop all jobs in the Cluster when entering blocked mode', function () {
      c = makeTest()
      var limiter1 = new Bottleneck({
        id: 'blocked',
        trackDoneStatus: true,
        datastore: process.env.DATASTORE,
        clearDatastore: true,

        maxConcurrent: 1,
        minTime: 50,
        highWater: 2,
        strategy: Bottleneck.strategy.BLOCK
      })
      var limiter2
      var client_num_queued_key = limiterKeys(limiter1)[5]

      return limiter1.ready()
      .then(function () {
        limiter2 = new Bottleneck({
          id: 'blocked',
          trackDoneStatus: true,
          datastore: process.env.DATASTORE,
          clearDatastore: false,
        })
        return limiter2.ready()
      })
      .then(function () {
        return Promise.all([
          limiter1.submit(c.slowJob, 100, null, 1, c.noErrVal(1)),
          limiter1.submit(c.slowJob, 100, null, 2, (err) => c.mustExist(err))
        ])
      })
      .then(function () {
        return Promise.all([
          limiter2.submit(c.slowJob, 100, null, 3, (err) => c.mustExist(err)),
          limiter2.submit(c.slowJob, 100, null, 4, (err) => c.mustExist(err)),
          limiter2.submit(c.slowJob, 100, null, 5, (err) => c.mustExist(err))
        ])
      })
      .then(function () {
        return runCommand(limiter1, 'hvals', [client_num_queued_key])
      })
      .then(function (queues) {
        c.mustEqual(queues, ['0', '0'])

        return Promise.all([
          c.limiter.clusterQueued(),
          limiter2.clusterQueued()
        ])
      })
      .then(function (queues) {
        c.mustEqual(queues, [0, 0])

        return c.wait(100)
      })
      .then(function () {
        var counts1 = limiter1.counts()
        c.mustEqual(counts1.RECEIVED, 0)
        c.mustEqual(counts1.QUEUED, 0)
        c.mustEqual(counts1.RUNNING, 0)
        c.mustEqual(counts1.EXECUTING, 0)
        c.mustEqual(counts1.DONE, 1)

        var counts2 = limiter2.counts()
        c.mustEqual(counts2.RECEIVED, 0)
        c.mustEqual(counts2.QUEUED, 0)
        c.mustEqual(counts2.RUNNING, 0)
        c.mustEqual(counts2.EXECUTING, 0)
        c.mustEqual(counts2.DONE, 0)

        return c.last()
      })
      .then(function (results) {
        c.checkResultsOrder([[1]])
        c.checkDuration(100)

        return Promise.all([
          limiter1.disconnect(false),
          limiter2.disconnect(false)
        ])
      })
    })

    it('Should pass messages to all limiters in Cluster', function (done) {
      c = makeTest({
        maxConcurrent: 1,
        minTime: 100,
        id: 'super-duper'
      })
      var limiter1 = new Bottleneck({
        maxConcurrent: 1,
        minTime: 100,
        id: 'super-duper',
        datastore: process.env.DATASTORE
      })
      var limiter2 = new Bottleneck({
        maxConcurrent: 1,
        minTime: 100,
        id: 'nope',
        datastore: process.env.DATASTORE
      })
      var received = []

      c.limiter.on('message', (msg) => {
        received.push(1, msg)
      })
      limiter1.on('message', (msg) => {
        received.push(2, msg)
      })
      limiter2.on('message', (msg) => {
        received.push(3, msg)
      })

      Promise.all([c.limiter.ready(), limiter2.ready()])
      .then(function () {
        limiter1.publish(555)
      })

      setTimeout(function () {
        limiter1.disconnect()
        limiter2.disconnect()
        c.mustEqual(received.sort(), [1, 2, '555', '555'])
        done()
      }, 150)
    })

    it('Should pass messages to correct limiter after Group re-instantiations', function () {
      c = makeTest()
      var group = new Bottleneck.Group({
        maxConcurrent: 1,
        minTime: 100,
        datastore: process.env.DATASTORE
      })
      var received = []

      return new Promise(function (resolve, reject) {
        var limiter = group.key('A')

        limiter.on('message', function (msg) {
          received.push('1', msg)
          return resolve()
        })
        limiter.publish('Bonjour!')
      })
      .then(function () {
        return new Promise(function (resolve, reject) {
          var limiter = group.key('B')

          limiter.on('message', function (msg) {
            received.push('2', msg)
            return resolve()
          })
          limiter.publish('Comment allez-vous?')
        })
      })
      .then(function () {
        return group.deleteKey('A')
      })
      .then(function () {
        return new Promise(function (resolve, reject) {
          var limiter = group.key('A')

          limiter.on('message', function (msg) {
            received.push('3', msg)
            return resolve()
          })
          limiter.publish('Au revoir!')
        })
      })
      .then(function () {
        c.mustEqual(received, ['1', 'Bonjour!', '2', 'Comment allez-vous?', '3', 'Au revoir!'])
        group.disconnect()
      })
    })

    it('Should have a default key TTL when using Groups', function () {
      c = makeTest()
      var group = new Bottleneck.Group({
        datastore: process.env.DATASTORE
      })

      return group.key('one').ready()
      .then(function () {
        var limiter = group.key('one')
        var settings_key = limiterKeys(limiter)[0]
        return runCommand(limiter, 'ttl', [settings_key])
      })
      .then(function (ttl) {
        assert(ttl >= 290 && ttl <= 305)
      })
      .then(function () {
        return group.disconnect(false)
      })
    })

    it('Should support Groups and expire Redis keys', function () {
      c = makeTest()
      var group = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        minTime: 50,
        timeout: 200
      })
      var limiter1
      var limiter2
      var limiter3

      var t0 = Date.now()
      var results = {}
      var job = function (x) {
        results[x] = Date.now() - t0
        return Promise.resolve()
      }

      return c.limiter.ready()
      .then(function () {
        limiter1 = group.key('one')
        limiter2 = group.key('two')
        limiter3 = group.key('three')

        return Promise.all([limiter1.ready(), limiter2.ready(), limiter3.ready()])
      })
      .then(function () {
        return Promise.all([countKeys(limiter1), countKeys(limiter2), countKeys(limiter3)])
      })
      .then(function (counts) {
        c.mustEqual(counts, [5, 5, 5])
        return Promise.all([
          limiter1.schedule(job, 'a'),
          limiter1.schedule(job, 'b'),
          limiter1.schedule(job, 'c'),
          limiter2.schedule(job, 'd'),
          limiter2.schedule(job, 'e'),
          limiter3.schedule(job, 'f')
        ])
      })
      .then(function () {
        c.mustEqual(Object.keys(results).length, 6)
        assert(results.a < results.b)
        assert(results.b < results.c)
        assert(results.b - results.a >= 40)
        assert(results.c - results.b >= 40)

        assert(results.d < results.e)
        assert(results.e - results.d >= 40)

        assert(Math.abs(results.a - results.d) <= 10)
        assert(Math.abs(results.d - results.f) <= 10)
        assert(Math.abs(results.b - results.e) <= 10)

        return c.wait(400)
      })
      .then(function () {
        return Promise.all([countKeys(limiter1), countKeys(limiter2), countKeys(limiter3)])
      })
      .then(function (counts) {
        c.mustEqual(counts, [0, 0, 0])
        c.mustEqual(group.keys().length, 0)
        c.mustEqual(Object.keys(group.connection.limiters).length, 0)
        return group.disconnect(false)
      })

    })

    it('Should not recreate a key when running heartbeat', function () {
      c = makeTest()
      var group = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        maxConcurrent: 50,
        minTime: 50,
        timeout: 300,
        heartbeatInterval: 5
      })
      var key = 'heartbeat'

      var limiter = group.key(key)
      return c.pNoErrVal(limiter.schedule(c.promise, null, 1), 1)
      .then(function () {
        return limiter.done()
      })
      .then(function (done) {
        c.mustEqual(done, 1)
        return c.wait(400)
      })
      .then(function () {
        return countKeys(limiter)
      })
      .then(function (count) {
        c.mustEqual(count, 0)
        return group.disconnect(false)
      })
    })

    it('Should delete Redis key when manually deleting a group key', function () {
      c = makeTest()
      var group1 = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        maxConcurrent: 50,
        minTime: 50,
        timeout: 300
      })
      var group2 = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        maxConcurrent: 50,
        minTime: 50,
        timeout: 300
      })
      var key = 'deleted'
      var limiter = group1.key(key) // only for countKeys() use

      return c.pNoErrVal(group1.key(key).schedule(c.promise, null, 1), 1)
      .then(function () {
        return c.pNoErrVal(group2.key(key).schedule(c.promise, null, 2), 2)
      })
      .then(function () {
        c.mustEqual(group1.keys().length, 1)
        c.mustEqual(group2.keys().length, 1)
        return group1.deleteKey(key)
      })
      .then(function (deleted) {
        c.mustEqual(deleted, true)
        return countKeys(limiter)
      })
      .then(function (count) {
        c.mustEqual(count, 0)
        c.mustEqual(group1.keys().length, 0)
        c.mustEqual(group2.keys().length, 1)
        return c.wait(200)
      })
      .then(function () {
        c.mustEqual(group1.keys().length, 0)
        c.mustEqual(group2.keys().length, 0)
        return Promise.all([
          group1.disconnect(false),
          group2.disconnect(false)
        ])
      })
    })

    it('Should delete Redis keys from a group even when the local limiter is not present', function () {
      c = makeTest()
      var group1 = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        maxConcurrent: 50,
        minTime: 50,
        timeout: 300
      })
      var group2 = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        maxConcurrent: 50,
        minTime: 50,
        timeout: 300
      })
      var key = 'deleted-cluster-wide'
      var limiter = group1.key(key) // only for countKeys() use

      return c.pNoErrVal(group1.key(key).schedule(c.promise, null, 1), 1)
      .then(function () {
        c.mustEqual(group1.keys().length, 1)
        c.mustEqual(group2.keys().length, 0)
        return group2.deleteKey(key)
      })
      .then(function (deleted) {
        c.mustEqual(deleted, true)
        return countKeys(limiter)
      })
      .then(function (count) {
        c.mustEqual(count, 0)
        c.mustEqual(group1.keys().length, 1)
        c.mustEqual(group2.keys().length, 0)
        return c.wait(200)
      })
      .then(function () {
        c.mustEqual(group1.keys().length, 0)
        c.mustEqual(group2.keys().length, 0)
        return Promise.all([
          group1.disconnect(false),
          group2.disconnect(false)
        ])
      })
    })

    it('Should returns all Group keys in the cluster', async function () {
      c = makeTest()
      var group1 = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'same',
        timeout: 3000
      })
      var group2 = new Bottleneck.Group({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'same',
        timeout: 3000
      })
      var keys1 = ['lorem', 'ipsum', 'dolor', 'sit', 'amet', 'consectetur']
      var keys2 = ['adipiscing', 'elit']
      var both = keys1.concat(keys2)

      await Promise.all(keys1.map((k) => group1.key(k).ready()))
      await Promise.all(keys2.map((k) => group2.key(k).ready()))

      c.mustEqual(group1.keys().sort(), keys1.sort())
      c.mustEqual(group2.keys().sort(), keys2.sort())
      c.mustEqual(
        (await group1.clusterKeys()).sort(),
        both.sort()
      )
      c.mustEqual(
        (await group1.clusterKeys()).sort(),
        both.sort()
      )

      var group3 = new Bottleneck.Group({ datastore: 'local' })
      c.mustEqual(await group3.clusterKeys(), [])

      await group1.disconnect(false)
      await group2.disconnect(false)
    })

    it('Should queue up the least busy limiter', async function () {
      c = makeTest()
      var limiter1 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var limiter2 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var limiter3 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var limiter4 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var runningOrExecuting = function (limiter) {
        var counts = limiter.counts()
        return counts.RUNNING + counts.EXECUTING
      }

      var resolve1, resolve2, resolve3, resolve4, resolve5, resolve6, resolve7
      var p1 = new Promise(function (resolve, reject) {
        resolve1 = function (err, n) { resolve(n) }
      })
      var p2 = new Promise(function (resolve, reject) {
        resolve2 = function (err, n) { resolve(n) }
      })
      var p3 = new Promise(function (resolve, reject) {
        resolve3 = function (err, n) { resolve(n) }
      })
      var p4 = new Promise(function (resolve, reject) {
        resolve4 = function (err, n) { resolve(n) }
      })
      var p5 = new Promise(function (resolve, reject) {
        resolve5 = function (err, n) { resolve(n) }
      })
      var p6 = new Promise(function (resolve, reject) {
        resolve6 = function (err, n) { resolve(n) }
      })
      var p7 = new Promise(function (resolve, reject) {
        resolve7 = function (err, n) { resolve(n) }
      })

      await limiter1.schedule({id: '1'}, c.promise, null, 'A')
      await limiter2.schedule({id: '2'}, c.promise, null, 'B')
      await limiter3.schedule({id: '3'}, c.promise, null, 'C')
      await limiter4.schedule({id: '4'}, c.promise, null, 'D')

      await limiter1.submit({id: 'A'}, c.slowJob, 50, null, 1, resolve1)
      await limiter1.submit({id: 'B'}, c.slowJob, 500, null, 2, resolve2)
      await limiter2.submit({id: 'C'}, c.slowJob, 550, null, 3, resolve3)

      c.mustEqual(runningOrExecuting(limiter1), 2)
      c.mustEqual(runningOrExecuting(limiter2), 1)

      await limiter3.submit({id: 'D'}, c.slowJob, 50, null, 4, resolve4)
      await limiter4.submit({id: 'E'}, c.slowJob, 50, null, 5, resolve5)
      await limiter3.submit({id: 'F'}, c.slowJob, 50, null, 6, resolve6)
      await limiter4.submit({id: 'G'}, c.slowJob, 50, null, 7, resolve7)

      c.mustEqual(limiter3.counts().QUEUED, 2)
      c.mustEqual(limiter4.counts().QUEUED, 2)

      await Promise.all([p1, p2, p3, p4, p5, p6, p7])

      c.checkResultsOrder([['A'],['B'],['C'],['D'],[1],[4],[5],[6],[7],[2],[3]])

      await limiter1.disconnect(false)
      await limiter2.disconnect(false)
      await limiter3.disconnect(false)
      await limiter4.disconnect(false)
    })

    it('Should pass the remaining capacity to other limiters', async function () {
      c = makeTest()
      var limiter1 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var limiter2 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var limiter3 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var limiter4 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'busy',
        timeout: 3000,
        maxConcurrent: 3,
        trackDoneStatus: true
      })
      var runningOrExecuting = function (limiter) {
        var counts = limiter.counts()
        return counts.RUNNING + counts.EXECUTING
      }
      var t3, t4

      var resolve1, resolve2, resolve3, resolve4, resolve5
      var p1 = new Promise(function (resolve, reject) {
        resolve1 = function (err, n) { resolve(n) }
      })
      var p2 = new Promise(function (resolve, reject) {
        resolve2 = function (err, n) { resolve(n) }
      })
      var p3 = new Promise(function (resolve, reject) {
        resolve3 = function (err, n) { t3 = Date.now(); resolve(n) }
      })
      var p4 = new Promise(function (resolve, reject) {
        resolve4 = function (err, n) { t4 = Date.now(); resolve(n) }
      })
      var p5 = new Promise(function (resolve, reject) {
        resolve5 = function (err, n) { resolve(n) }
      })

      await limiter1.schedule({id: '1'}, c.promise, null, 'A')
      await limiter2.schedule({id: '2'}, c.promise, null, 'B')
      await limiter3.schedule({id: '3'}, c.promise, null, 'C')
      await limiter4.schedule({id: '4'}, c.promise, null, 'D')

      await limiter1.submit({id: 'A', weight: 2}, c.slowJob, 50, null, 1, resolve1)
      await limiter2.submit({id: 'C'}, c.slowJob, 550, null, 2, resolve2)

      c.mustEqual(runningOrExecuting(limiter1), 1)
      c.mustEqual(runningOrExecuting(limiter2), 1)

      await limiter3.submit({id: 'D'}, c.slowJob, 50, null, 3, resolve3)
      await limiter4.submit({id: 'E'}, c.slowJob, 50, null, 4, resolve4)
      await limiter4.submit({id: 'G'}, c.slowJob, 50, null, 5, resolve5)

      c.mustEqual(limiter3.counts().QUEUED, 1)
      c.mustEqual(limiter4.counts().QUEUED, 2)

      await Promise.all([p1, p2, p3, p4, p5])

      c.checkResultsOrder([['A'],['B'],['C'],['D'],[1],[3],[4],[5],[2]])

      assert(Math.abs(t3 - t4) < 15)

      await limiter1.disconnect(false)
      await limiter2.disconnect(false)
      await limiter3.disconnect(false)
      await limiter4.disconnect(false)
    })

    it('Should take the capacity and blacklist if the priority limiter is not responding', async function () {
      c = makeTest()
      var limiter1 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'crash',
        timeout: 3000,
        maxConcurrent: 1,
        trackDoneStatus: true
      })
      var limiter2 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'crash',
        timeout: 3000,
        maxConcurrent: 1,
        trackDoneStatus: true
      })
      var limiter3 = new Bottleneck({
        datastore: process.env.DATASTORE,
        clearDatastore: true,
        id: 'crash',
        timeout: 3000,
        maxConcurrent: 1,
        trackDoneStatus: true
      })

      await limiter1.schedule({id: '1'}, c.promise, null, 'A')
      await limiter2.schedule({id: '2'}, c.promise, null, 'B')
      await limiter3.schedule({id: '3'}, c.promise, null, 'C')

      var resolve1, resolve2, resolve3
      var p1 = new Promise(function (resolve, reject) {
        resolve1 = function (err, n) { resolve(n) }
      })
      var p2 = new Promise(function (resolve, reject) {
        resolve2 = function (err, n) { resolve(n) }
      })
      var p3 = new Promise(function (resolve, reject) {
        resolve3 = function (err, n) { resolve(n) }
      })

      await limiter1.submit({id: '4'}, c.slowJob, 100, null, 4, resolve1)
      await limiter2.submit({id: '5'}, c.slowJob, 100, null, 5, resolve2)
      await limiter3.submit({id: '6'}, c.slowJob, 100, null, 6, resolve3)
      await limiter2.disconnect(false)

      await Promise.all([p1, p3])
      c.checkResultsOrder([['A'], ['B'], ['C'], [4], [6]])

      await limiter1.disconnect(false)
      await limiter2.disconnect(false)
      await limiter3.disconnect(false)
    })

  })
}
