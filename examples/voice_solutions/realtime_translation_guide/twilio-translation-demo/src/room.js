export class TranslationRoom {
  constructor({ createBridge, logger = console }) {
    this.createBridge = createBridge;
    this.logger = logger;
    this.waiting = [];
    this.callers = new Map();
    this.pairs = new Map();
  }

  addCaller(caller) {
    const existing = this.callers.get(caller.callSid);
    if (existing && existing !== caller) {
      this.removeCaller(caller.callSid, existing);
      existing.close?.();
    }

    this.callers.set(caller.callSid, caller);

    const waitingCaller = this.waiting.find(
      (candidate) => candidate.callSid !== caller.callSid,
    );
    if (!waitingCaller) {
      if (!this.waiting.includes(caller)) {
        this.waiting.push(caller);
      }
      this.logger.info?.(`[room] ${caller.callSid} waiting in ${caller.language}`);
      return null;
    }

    this.waiting = this.waiting.filter(
      (candidate) => candidate.callSid !== waitingCaller.callSid,
    );
    return this.#pairCallers(waitingCaller, caller);
  }

  handleMedia(callSid, payload) {
    const caller = this.callers.get(callSid);
    caller?.bridgeToPeer?.sendTwilioMedia(payload);
  }

  removeCaller(callSid, expectedCaller) {
    const caller = this.callers.get(callSid);
    if (expectedCaller && caller !== expectedCaller) {
      return;
    }

    this.waiting = this.waiting.filter((candidate) =>
      expectedCaller ? candidate !== expectedCaller : candidate.callSid !== callSid,
    );
    if (!caller) {
      return;
    }
    this.callers.delete(callSid);

    const pair = caller.pairId ? this.pairs.get(caller.pairId) : null;
    if (!pair) {
      return;
    }

    pair.a.bridgeToPeer?.close();
    pair.b.bridgeToPeer?.close();
    this.pairs.delete(pair.id);
    this.callers.delete(pair.a.callSid);
    this.callers.delete(pair.b.callSid);

    if (pair.a.callSid !== callSid) {
      pair.a.close?.();
    }
    if (pair.b.callSid !== callSid) {
      pair.b.close?.();
    }
  }

  status() {
    return {
      activeCallers: this.callers.size,
      activePairs: this.pairs.size,
      waiting: this.waiting.length,
    };
  }

  #pairCallers(a, b) {
    const id = `${a.callSid}:${b.callSid}`;
    let aBridge = null;
    let bBridge = null;
    try {
      aBridge = this.createBridge({
        sourceLabel: a.callSid,
        target: b,
        targetLanguage: b.language,
      });
      bBridge = this.createBridge({
        sourceLabel: b.callSid,
        target: a,
        targetLanguage: a.language,
      });
    } catch (error) {
      aBridge?.close?.();
      bBridge?.close?.();
      this.callers.delete(a.callSid);
      this.callers.delete(b.callSid);
      a.close?.();
      b.close?.();
      throw error;
    }

    a.pairId = id;
    b.pairId = id;
    a.bridgeToPeer = aBridge;
    b.bridgeToPeer = bBridge;

    const pair = { id, a, b };
    this.pairs.set(id, pair);
    this.logger.info?.(
      `[room] paired ${a.callSid} (${a.language}) <-> ${b.callSid} (${b.language})`,
    );
    return pair;
  }
}
