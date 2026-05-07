export class TranslationRoom {
  constructor({ createBridge, logger = console }) {
    this.createBridge = createBridge;
    this.logger = logger;
    this.waiting = [];
    this.callers = new Map();
    this.pairs = new Map();
  }

  addCaller(caller) {
    this.callers.set(caller.callSid, caller);

    const waitingCaller = this.waiting.find(
      (candidate) => candidate.callSid !== caller.callSid,
    );
    if (!waitingCaller) {
      this.waiting.push(caller);
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

  removeCaller(callSid) {
    this.waiting = this.waiting.filter((caller) => caller.callSid !== callSid);
    const caller = this.callers.get(callSid);
    this.callers.delete(callSid);

    const pair = caller?.pairId ? this.pairs.get(caller.pairId) : null;
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
    a.pairId = id;
    b.pairId = id;
    a.bridgeToPeer = this.createBridge({
      sourceLabel: a.callSid,
      target: b,
      targetLanguage: b.language,
    });
    b.bridgeToPeer = this.createBridge({
      sourceLabel: b.callSid,
      target: a,
      targetLanguage: a.language,
    });

    const pair = { id, a, b };
    this.pairs.set(id, pair);
    this.logger.info?.(
      `[room] paired ${a.callSid} (${a.language}) <-> ${b.callSid} (${b.language})`,
    );
    return pair;
  }
}
