import { createHash } from 'node:crypto';
import { settingsEquivalent, matchesTarget as apiMatchesTarget } from './admin-api.mjs';
import { configDigest, validateConfig, validateSnapshot, planTarget, historyRange, requireThat, amount, time, fail, HOUR } from './policy.mjs';
import { validateEnrollment, enrollmentHash } from './enrollment.mjs';

const keyHash = key => createHash('sha256').update(key).digest('hex').slice(0, 24);
function matchesTarget(snapshot, pending, config) {
  return apiMatchesTarget(snapshot, {amount: pending.amount, unit: config.unit, periodEnd: config.period.end});
}
const sameSettings = (a, b, unit) => settingsEquivalent(a.settings, b.settings, unit);
const sameInherited = (a, b, unit) => settingsEquivalent(a.settings, { ...a.settings, inherited: b.settings.inherited }, unit);

/** One shared state machine for all runners. PATCHes use persisted absolute targets.
 * A lock cannot fence manual administrators: the public API has no compare-and-swap.
 * Use one writer and coordinate manual changes for the enrolled users.
 */
export async function execute({ config, enrollment, api, store, now: fixedNow, clock = () => new Date().toISOString(), apply = false,
  restore = false, resumeAuth = false, cancelInitial = false, shouldContinue = () => true }) {
  const now = fixedNow ?? clock();
  const readNow = () => fixedNow ?? clock();
  validateEnrollment(config, enrollment, now, apply);
  const mode = restore ? 'restore' : apply ? 'apply' : 'preview';
  if (apply) requireThat(config.liveWrites || api.synthetic === true, 'LIVE_WRITES_DISABLED');
  const ctx = validateConfig(config, now);
  const members = await api.listMembers();
  const roster = new Set(members);
  requireThat(roster.size === members.length, 'ROSTER_DUPLICATES');
  const added = config.cohort.mode === 'all' ? members.filter(id => !enrollment.members.some(member => member.userId === id)).length : 0;
  let next = 0;
  const results = new Array(enrollment.members.length);
  async function runMember(member) {
    const key = `${config.workspaceId}:${member.userId}`;
    const base = { controllerKey: keyHash(key), userId: member.userId, workspaceId: config.workspaceId,
      mode, observedAt: now, slot: ctx.slot, unit: config.unit };
    return store.withLock(key, async () => {
      let state = await store.getState(key);
      const receipt = async details => {
        const value = { ...base, ...details };
        await store.putReceipt(value);
        return value;
      };
      try {
        if (!roster.has(member.userId)) return receipt({ok:false,status:'attention',code:'MEMBER_REMOVED_OR_INELIGIBLE'});
        if (state) {
          requireThat(state.configDigest === configDigest(config) && state.enrollmentHash === enrollmentHash(enrollment), 'POLICY_OR_ENROLLMENT_CHANGED_STOP_AND_RESTORE_FIRST');
          if(state.halted && !resumeAuth) throw fail('AUTH_FAILURE_HALTED_REVIEW_REQUIRED');
          requireThat(state.lastSlot === undefined || ctx.slot >= state.lastSlot, 'CLOCK_MOVED_BACKWARD');
        }
        let current = await api.readSnapshot(member.userId);
        validateSnapshot(current, config, member.userId, readNow());
        if(cancelInitial) {
          requireThat(!apply && !restore, 'CANCEL_IS_READ_ONLY');
          if(!state?.pending || state.last)return receipt({ok:true,status:'no_unapplied_initial_intent'});
          requireThat(state.pending.kind==='cap' && sameSettings(current,state.pending.before,config.unit), 'CANCEL_REQUIRES_UNCHANGED_BEFORE_STATE');
          state={...state,pending:null,last:current,lastUsage:current.usage,lastSlot:ctx.slot,restored:true};
          await store.putState(key,state);
          return receipt({ok:true,status:'initial_intent_cancelled',action:'No cap was changed. This member is closed for this enrollment; review a new pilot if needed.'});
        }
        if(resumeAuth) {
          requireThat(!apply && !restore, 'RESUME_IS_READ_ONLY');
          if(!state?.halted)return receipt({ok:true,status:'not_halted'});
          requireThat(state.pending && (sameSettings(current,state.pending.before,config.unit) ||
            (state.pending.kind==='restore' ? settingsEquivalent(current.settings,state.original.settings,config.unit) : matchesTarget(current,state.pending,config))), 'RESUME_CURRENT_STATE_CONFLICT');
          state.halted=false;
          await store.putState(key,state);
          return receipt({ok:true,status:'auth_resumed',action:'No cap was changed. Preview and rerun the saved operation explicitly.'});
        }
        if (state?.lastUsage !== undefined) requireThat(amount(current.usage) >= amount(state.lastUsage), 'COUNTER_DECREASE_REQUIRES_PERIOD_REVIEW');
        if (state?.pending) {
          const pending = state.pending;
          const completed = pending.kind === 'restore' ? settingsEquivalent(current.settings, state.original.settings, config.unit) : matchesTarget(current, pending, config) && sameInherited(current,pending.before,config.unit);
          if (completed) {
            if (!apply) return receipt({ ok: true, status: 'pending_already_applied', action: 'Rerun with --apply to record reconciliation; no new target is calculated.' });
            state = { ...state, pending: null, last: current, lastUsage: current.usage, lastSlot: pending.slot,
              restored: pending.kind === 'restore' };
            await store.putState(key, state);
            return receipt({ ok: true, status: 'reconciled', amount: current.cap.amount, restored: state.restored });
          }
          requireThat(sameSettings(current, pending.before, config.unit), 'PENDING_WRITE_CONFLICT');
          if(pending.kind==='cap' && pending.plan?.wouldRestrict) {
            requireThat(time(readNow())-time(enrollment.capturedAt)<=15*60_000,'INITIAL_RESTRICTION_PREVIEW_EXPIRED_CANCEL_AND_REVIEW');
            requireThat(validateConfig(config,readNow()).slot===pending.slot,'INITIAL_RESTRICTION_SLOT_EXPIRED_CANCEL_AND_REVIEW');
          }
          if (state.notBefore) requireThat(time(readNow()) >= time(state.notBefore), 'RETRY_AFTER_NOT_REACHED');
          if (!apply) return receipt({ ok: true, status: 'pending_retry_preview', pending });
          requireThat(restore === (pending.kind === 'restore'), 'RECONCILE_ORIGINAL_OPERATION_FIRST');
          return await writePending(state, current);
        }
        if (state?.restored) return receipt({ ok: true, status: 'restored_stopped', action: 'This enrollment is closed; create and review a new enrollment for another period or policy.' });
        if (state?.last) requireThat(sameSettings(current, state.last, config.unit), 'MANUAL_ADMIN_CHANGE_CONFLICT');
        else {
          requireThat(sameSettings(current, member.before, config.unit), 'ENROLLMENT_BEFORE_STATE_CHANGED');
          requireThat(time(now) - time(enrollment.capturedAt) <= 15 * 60_000, 'INITIAL_PREVIEW_EXPIRED_RECAPTURE');
          requireThat(ctx.slot === member.plan.slot, 'INITIAL_PREVIEW_SLOT_CHANGED_RECAPTURE');
        }
        if (restore) {
          if (!state) return receipt({ ok: true, status: 'nothing_owned' });
          requireThat(sameInherited(current,state.original,config.unit), 'ORIGINAL_INHERITED_SOURCE_CHANGED');
          if (!apply) return receipt({ ok: true, status: 'restore_preview', before: current, after: state.original });
          state.pending = { kind: 'restore', before: current, slot: state.lastSlot };
        } else {
          if (state?.lastSlot === ctx.slot) return receipt({ ok: true, status: 'duplicate_slot', amount: current.cap.amount });
          const history = config.policy.pattern === 'observed_headroom' ? await api.readHistory(member.userId, historyRange(config, now)) : undefined;
          const plan = state ? planTarget(config, current, readNow(), history) : member.plan;
          requireThat(plan.slot === ctx.slot, 'SLOT_CHANGED_DURING_RUN');
          requireThat(amount(plan.amount) <= amount(config.policy.ceiling), 'TARGET_ABOVE_CEILING');
          if (plan.wouldRestrict) {
            requireThat(!state && config.allowInitialReduction, 'INITIAL_REDUCTION_REQUIRES_REVIEWED_OPT_IN');
            requireThat(amount(current.usage) === amount(member.before.usage), 'RESTRICTION_USAGE_CHANGED_RECAPTURE');
          }
          if (!apply) return receipt({ ok: true, status: 'preview', before: current, plan });
          if (!state) state = { version: 1, configDigest: configDigest(config), enrollmentHash: enrollmentHash(enrollment), original: member.before };
          // A no-op still consumes the slot. Late history corrections cannot re-award it.
          if (current.cap.type === 'limited' && amount(current.cap.amount) === amount(plan.amount) && current.cap.source === 'individual_override' && current.cap.expiresAt === config.period.end) {
            state = { ...state, last: current, lastUsage: current.usage, lastSlot: ctx.slot };
            await store.putState(key, state);
            return receipt({ ok: true, status: 'held', plan });
          }
          state.pending = { kind: 'cap', before: current, amount: plan.amount, slot: ctx.slot, plan };
        }
        await store.putState(key, state); // Durable intent MUST precede any external mutation.
        return await writePending(state, current);

        async function writePending(saved, before) {
          // Re-read while holding the controller lock. There is still a manual-admin race
          // between this read and PATCH because the API has no conditional update.
          requireThat(shouldContinue(), 'INVOCATION_DEADLINE_REACHED');
          const activeNow = await api.listMembers();
          requireThat(activeNow.includes(member.userId), 'MEMBER_REMOVED_BEFORE_WRITE');
          const fresh = await api.readSnapshot(member.userId);
          validateSnapshot(fresh, config, member.userId, readNow());
          requireThat(validateConfig(config, readNow()).slot === ctx.slot, 'SLOT_CHANGED_DURING_RUN');
          requireThat(sameSettings(fresh, before, config.unit), 'FINAL_READ_CONFLICT');
          requireThat(amount(fresh.usage) >= amount(before.usage), 'COUNTER_DECREASE_REQUIRES_PERIOD_REVIEW');
          if (saved.pending.kind === 'cap' && saved.pending.plan?.wouldRestrict) requireThat(amount(fresh.usage) === amount(member.before.usage), 'RESTRICTION_USAGE_CHANGED_RECAPTURE');
          if(saved.pending.kind==='cap' && saved.pending.plan?.wouldRestrict) {
            requireThat(time(readNow())-time(enrollment.capturedAt)<=15*60_000,'INITIAL_RESTRICTION_PREVIEW_EXPIRED_CANCEL_AND_REVIEW');
            requireThat(validateConfig(config,readNow()).slot===saved.pending.slot,'INITIAL_RESTRICTION_SLOT_EXPIRED_CANCEL_AND_REVIEW');
          }
          await store.assertLock(key);
          requireThat(time(config.period.end) - time(fresh.observedAt) >= 30_000, 'TOO_CLOSE_TO_PERIOD_END');
          const notAfter = saved.pending.kind==='cap' && saved.pending.plan?.wouldRestrict
            ? new Date(Math.min(time(enrollment.capturedAt)+15*60_000,
              time(config.policy.anchor)+(saved.pending.slot+1)*config.policy.intervalHours*HOUR,time(config.period.end))).toISOString()
            : config.period.end;
          const target = { amount: saved.pending.amount, unit: config.unit, periodEnd: config.period.end, expectedSettings: fresh.settings,
            notAfter,
            ...(saved.pending.plan?.wouldRestrict ? {expectedUsage: member.before.usage} : {}) };
          if (saved.pending.kind === 'restore') await api.restore(member.userId, { settings: saved.original.settings, unit: config.unit, periodEnd: config.period.end, expectedSettings: fresh.settings });
          else await api.setCap(member.userId, target);
          const after = await api.readSnapshot(member.userId);
          validateSnapshot(after, config, member.userId, readNow());
          requireThat(saved.pending.kind === 'restore' ? settingsEquivalent(after.settings, saved.original.settings, config.unit) : matchesTarget(after, saved.pending, config) && sameInherited(after,saved.pending.before,config.unit), 'WRITE_READBACK_MISMATCH');
          const details = saved.pending;
          state = { ...saved, pending: null, last: after, lastUsage: after.usage, lastSlot: details.slot,
            restored: details.kind === 'restore', notBefore: null };
          await store.putState(key, state);
          return receipt({ ok: true, status: details.kind === 'restore' ? 'restored' : 'applied', before, after, plan: details.plan });
        }
      } catch (error) {
        // Only persist generic error codes; never retain API bodies or credentials.
        if (apply && state?.pending) {
          if (error.status === 401 || error.status === 403) state.halted = true;
          // A delay beyond this period stops this enrollment entirely; never shorten
          // Retry-After into an earlier eligible retry.
          if (Number.isFinite(error.retryAfterMs) && error.retryAfterMs > 0) state.notBefore = new Date(Math.min(time(readNow()) + error.retryAfterMs, time(config.period.end))).toISOString();
          await store.putState(key, state);
        }
        return receipt({ ok: false, status: 'attention', code: error.code ?? 'CONTROLLER_ERROR',
          action: state?.pending ? 'Inspect saved intent and live settings. Rerun the same operation after resolving the reported condition; do not delete state.' : 'Review the enrollment and current settings before another run.' });
      }
    });
  }
  await Promise.all(Array.from({ length: Math.min(config.concurrency, enrollment.members.length) }, async () => {
    for (;;) {
      const index = next++;
      if (index >= enrollment.members.length) return;
      if (!shouldContinue()) { results[index] = { userId: enrollment.members[index].userId, ok: false, status: 'deferred', code: 'INVOCATION_DEADLINE_REACHED' }; continue; }
      try { results[index] = await runMember(enrollment.members[index]); }
      catch (error) { results[index] = { userId: enrollment.members[index].userId, ok: false, status: 'attention', code: error.code ?? 'STORE_OR_API_FAILURE' }; }
    }
  }));
  return { ok: results.every(result => result.ok), mode, addedMembersNotEnrolled: added, results };
}
