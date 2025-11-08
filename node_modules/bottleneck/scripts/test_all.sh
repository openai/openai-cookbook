#!/usr/bin/env bash

set -e

source .env

echo 'ioredis tests'
DATASTORE=ioredis npm test

echo 'NodeRedis tests'
DATASTORE=redis npm test

echo 'ES5 bundle tests'
BUILD=es5 npm test

echo 'Light bundle tests'
BUILD=light npm test

echo 'Local tests'
npm test
