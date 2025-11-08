if (process.env.BUILD === 'es5') {
  module.exports = require('../es5.js')
} else if (process.env.BUILD === 'light') {
  module.exports = require('../light.js')
} else {
  module.exports = require('../lib/index.js')
}
