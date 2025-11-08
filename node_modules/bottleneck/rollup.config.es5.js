import json from 'rollup-plugin-json';
import resolve from 'rollup-plugin-node-resolve';
import commonjs from 'rollup-plugin-commonjs';
import babel from 'rollup-plugin-babel';

const bannerLines = [
  'This file contains the full Bottleneck library (MIT) compiled to ES5.',
  'https://github.com/SGrondin/bottleneck',
  'It also contains the regenerator-runtime (MIT), necessary for Babel-generated ES5 code to execute promise and async/await code.',
  'See the following link for Copyright and License information:',
  'https://github.com/facebook/regenerator/blob/master/packages/regenerator-runtime/runtime.js',
].map(x => `  * ${x}`).join('\n');
const banner = `/**\n${bannerLines}\n  */`;

export default {
  input: 'lib/es5.js',
  output: {
    name: 'Bottleneck',
    file: 'es5.js',
    sourcemap: false,
    globals: {},
    format: 'umd',
    banner
  },
  external: [],
  plugins: [
    json(),
    resolve(),
    commonjs(),
    babel({
      exclude: 'node_modules/**'
    })
  ]
};
