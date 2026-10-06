// Kept self-contained so the exact same policy can run inside QuickJS when a
// space is published and in the server before an embedded agent uses a tool.
export function validateAgentConfig(meta) {
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const reserved = key => ['__proto__', 'prototype', 'constructor'].includes(key);
  const reservedArgument = key => reserved(key) || ['type', 'actor', 'actorId', 'revisionId'].includes(key);
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value));
  const fail = message => { throw new Error(message); };
  const keys = (value, allowed, label) => {
    if (Object.keys(value).some(key => reserved(key) || !allowed.includes(key))) {
      fail(`${label} contains an unsupported or reserved field.`);
    }
  };
  const shortText = (value, limit, label) => {
    if (typeof value !== 'string' || !value.trim() || value.length > limit) fail(`${label} must be a nonempty string up to ${limit} characters.`);
  };
  if (!record(meta)) fail('Agent metadata must be an object.');
  const enabled = Array.isArray(meta.capabilities) && meta.capabilities.includes('space-agent');
  if (!enabled) {
    if (own(meta, 'agent')) fail('meta.agent requires the space-agent capability.');
    return undefined;
  }
  const config = meta.agent;
  if (!record(config)) fail('The space-agent capability requires meta.agent.');
  keys(config, ['instructions', 'actions', 'paintContext'], 'meta.agent');
  shortText(config.instructions, 4000, 'Agent instructions');
  if (own(config, 'paintContext')) {
    const paint = config.paintContext;
    if (!record(paint)) fail('Agent paintContext must be an object.');
    keys(paint, ['canvasKey', 'namespace'], 'Agent paintContext');
    for (const key of ['canvasKey', 'namespace']) {
      if (typeof paint[key] !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(paint[key]) || reserved(paint[key])) {
        fail(`Agent paintContext ${key} must be a safe identifier of up to 64 characters.`);
      }
    }
  }
  if (own(config, 'actions') && (!Array.isArray(config.actions) || config.actions.length > 6)) {
    fail('An embedded agent may declare up to six actions.');
  }
  let nodes = 0;
  const seen = new Set();
  function schema(value, depth) {
    if (++nodes > 100 || depth > 6) fail('Agent action schemas are too large or nested too deeply.');
    if (!record(value) || seen.has(value)) fail('An agent action schema must be a noncyclic object.');
    seen.add(value);
    const type = value.type;
    const fields = {
      object: ['properties', 'required', 'additionalProperties'],
      array: ['items', 'minItems', 'maxItems'],
      string: ['minLength', 'maxLength'],
      integer: ['minimum', 'maximum'],
      number: ['minimum', 'maximum'],
      boolean: [],
    };
    if (typeof type !== 'string' || !own(fields, type)) fail('Agent action schemas must use a supported JSON type.');
    keys(value, ['type', 'description', 'enum', ...fields[type]], 'Agent action schema');
    if (own(value, 'description')) shortText(value.description, 700, 'Schema description');
    const bounds = (low, high, maximum, requiredHigh = false) => {
      for (const name of [low, high]) {
        if (own(value, name) && (!Number.isInteger(value[name]) || value[name] < 0 || value[name] > maximum)) {
          fail(`Schema ${name} must be a whole number from 0 to ${maximum}.`);
        }
      }
      if (requiredHigh && !own(value, high)) fail(`Agent array schemas require ${high}.`);
      if (own(value, low) && own(value, high) && value[low] > value[high]) fail(`Schema ${low} cannot exceed ${high}.`);
    };
    if (type === 'object') {
      if (!record(value.properties) || Object.keys(value.properties).length > 40 || value.additionalProperties !== false) {
        fail('Agent object schemas require up to 40 properties and additionalProperties: false.');
      }
      for (const [name, child] of Object.entries(value.properties)) {
        if (!name || name.length > 64 || reservedArgument(name)) fail('An agent action property has an invalid or reserved name.');
        schema(child, depth + 1);
      }
      if (own(value, 'required') && (!Array.isArray(value.required)
        || value.required.length > 40 || new Set(value.required).size !== value.required.length
        || value.required.some(name => typeof name !== 'string' || !own(value.properties, name)))) {
        fail('Schema required must list distinct declared property names.');
      }
    } else if (type === 'array') {
      bounds('minItems', 'maxItems', 400, true);
      schema(value.items, depth + 1);
    } else if (type === 'string') {
      bounds('minLength', 'maxLength', 8000);
    } else if (type === 'number' || type === 'integer') {
      for (const name of ['minimum', 'maximum']) {
        if (own(value, name) && !Number.isFinite(value[name])) fail(`Schema ${name} must be finite.`);
      }
      if (own(value, 'minimum') && own(value, 'maximum') && value.minimum > value.maximum) fail('Schema minimum cannot exceed maximum.');
    }
    if (own(value, 'enum')) {
      if (['array', 'object'].includes(type) || !Array.isArray(value.enum) || value.enum.length < 1 || value.enum.length > 40) {
        fail('Schema enum must contain 1 to 40 primitive values.');
      }
      const matches = item => type === 'string'
        ? typeof item === 'string' && item.length <= 8000 && (!own(value, 'minLength') || [...item].length >= value.minLength) && (!own(value, 'maxLength') || [...item].length <= value.maxLength)
        : type === 'boolean' ? typeof item === 'boolean'
          : Number.isFinite(item) && (type !== 'integer' || Number.isInteger(item)) && (!own(value, 'minimum') || item >= value.minimum) && (!own(value, 'maximum') || item <= value.maximum);
      if (value.enum.some(item => !matches(item)) || new Set(value.enum).size !== value.enum.length) fail('Schema enum values must be distinct and match their type and bounds.');
    }
    seen.delete(value);
  }
  const names = new Set();
  for (const action of config.actions || []) {
    if (!record(action)) fail('Each agent action must be an object.');
    keys(action, ['name', 'description', 'parameters'], 'Agent action');
    if (typeof action.name !== 'string' || !/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(action.name) || reserved(action.name) || names.has(action.name)) {
      fail('Agent actions require unique, nonreserved names containing letters, digits, and underscores.');
    }
    names.add(action.name);
    shortText(action.description, 700, 'Agent action description');
    if (!record(action.parameters) || action.parameters.type !== 'object') fail('Agent action parameters must have an object schema.');
    schema(action.parameters, 0);
  }
  return config;
}

export function validateAgentAction(config, name, args) {
  validateAgentConfig({ capabilities: ['space-agent'], agent: config });
  const action = config.actions?.find(item => item.name === name);
  if (!action) throw new Error('The embedded agent requested an undeclared action.');
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
    && [Object.prototype, null].includes(Object.getPrototypeOf(value));
  const seen = new Set();
  let entries = 0;
  function json(value, depth = 0) {
    if (depth > 7 || ++entries > 4000) throw new Error('Agent action arguments are too large or nested too deeply.');
    if (value === null || typeof value === 'string' || typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value))) return;
    if ((!Array.isArray(value) && !record(value)) || seen.has(value)) throw new Error('Agent action arguments must contain only noncyclic JSON values.');
    seen.add(value);
    for (const [key, child] of Object.entries(value)) {
      if (['__proto__', 'prototype', 'constructor', 'type', 'actor', 'actorId', 'revisionId'].includes(key)) throw new Error('Agent action arguments contain a reserved property.');
      json(child, depth + 1);
    }
    seen.delete(value);
  }
  json(args);
  if (JSON.stringify(args).length > 8000) throw new Error('Agent action arguments must not exceed 8000 characters.');
  function matches(value, schema, path) {
    const invalid = message => { throw new Error(`Invalid agent action argument ${path}: ${message}.`); };
    const type = schema.type;
    if (type === 'object') {
      if (!record(value)) invalid('expected an object');
      for (const required of schema.required || []) if (!own(value, required)) invalid(`missing ${required}`);
      for (const [key, child] of Object.entries(value)) {
        if (!own(schema.properties, key)) invalid(`unexpected field ${key}`);
        matches(child, schema.properties[key], `${path}.${key}`);
      }
    } else if (type === 'array') {
      if (!Array.isArray(value)) invalid('expected an array');
      if (value.length < (schema.minItems || 0) || value.length > schema.maxItems) invalid('array length is outside its bounds');
      for (let index = 0; index < value.length; index++) matches(value[index], schema.items, `${path}[${index}]`);
    } else if (type === 'string') {
      if (typeof value !== 'string') invalid('expected a string');
      const length = [...value].length;
      if (length < (schema.minLength || 0) || (own(schema, 'maxLength') && length > schema.maxLength)) invalid('string length is outside its bounds');
    } else if (type === 'boolean') {
      if (typeof value !== 'boolean') invalid('expected a boolean');
    } else {
      if (!Number.isFinite(value) || (type === 'integer' && !Number.isInteger(value))) invalid(`expected a finite ${type}`);
      if ((own(schema, 'minimum') && value < schema.minimum) || (own(schema, 'maximum') && value > schema.maximum)) invalid('number is outside its bounds');
    }
    if (schema.enum && !schema.enum.includes(value)) invalid('value is not in its enum');
  }
  matches(args, action.parameters, 'parameters');
  return args;
}

export function validateAgentMessages(input) {
  const invalid = message => { throw Object.assign(new Error(message), { status: 400 }); };
  if (!Array.isArray(input) || input.length < 1 || input.length > 11 || input.length % 2 !== 1) {
    invalid('Send up to five exchanges followed by your message.');
  }
  let size = 0;
  const messages = input.map((message, index) => {
    const role = index % 2 === 0 ? 'user' : 'assistant';
    if (!message || typeof message !== 'object' || Array.isArray(message)
      || ![Object.prototype, null].includes(Object.getPrototypeOf(message))
      || Object.keys(message).some(key => !['role', 'content'].includes(key))
      || message.role !== role || typeof message.content !== 'string') {
      invalid('The conversation has an invalid message.');
    }
    const content = message.content.trim();
    const limit = role === 'user' ? 1200 : 6000;
    if (!content || content.length > limit || content.includes('\u0000')) {
      invalid(`Keep each ${role === 'user' ? 'message' : 'answer'} within ${limit} characters.`);
    }
    size += content.length;
    return { role, content };
  });
  if (size > 16_000) invalid('Start a new conversation to make room for this message.');
  return messages;
}
