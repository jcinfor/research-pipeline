"""E7-XL corpus: extends E7-long from 73 turns to ~175 turns (~16 weeks).

Adds 8 more weeks after E7-long's Jun 12 retro:
  Week 9  — Jun 15-19: passkey 100% rollout; retro scheduled
  Week 10 — Jun 22-26: Q3 planning; Alice proposes observability roadmap
  Week 11 — Jun 29-Jul 3: Security audit; Alice leads
  Week 12 — Jul 6-10: Product pivot; Carol explores social feature
  Week 13 — Jul 13-17: Dave builds session-sharing API; hits a bug
  Week 14 — Jul 20-24: Customer issue — Frank triages; references earlier fixes
  Week 15 — Jul 27-31: Release; Bob infra updates
  Week 16 — Aug 3-7:   Q2 retro; many recall questions spanning 16 weeks

Tests whether E7-long's "extraction systems converge at 9/10" pattern holds
at 2-3× the scale, or whether mem0's overwrite collisions finally bite and
zep's context-length concern materializes.
"""
from __future__ import annotations

from benchmarks.e1_blackboard_stress.corpus import Doc
from benchmarks.e7_long_conversational.corpus import (
    ALL_TURNS as E7_LONG_TURNS,
)


def _turn(session: int, turn: int, date: str, hour_min: str, speaker: str, text: str) -> Doc:
    return Doc(
        id=f"s{session:02d}_t{turn:02d}",
        pub_date=f"{date}T{hour_min}:00",
        text=f"[{speaker}] {text}",
        entities=tuple(),
    )


# =========================================================================
# Week 9 (Jun 15-19): Passkey 100%; retro scheduled
# =========================================================================

SESSION_12: tuple[Doc, ...] = (
    _turn(12, 1, "2026-06-15", "09:00", "user",
          "Passkey rollout is at 100% as of this morning. No new issues "
          "reported from Dave's team over the weekend."),
    _turn(12, 2, "2026-06-16", "14:00", "user",
          "Carol scheduling the quarterly retro for July 8. She wants "
          "engineering, design, and ops in one room."),
    _turn(12, 3, "2026-06-17", "10:00", "user",
          "Alice is asking for scope on her new observability work. She "
          "proposed building a cross-service tracing dashboard."),
    _turn(12, 4, "2026-06-17", "10:05", "assistant",
          "That's aligned with the platform-team charter. Given her auth "
          "background, tracing auth flows end-to-end would be high leverage."),
    _turn(12, 5, "2026-06-18", "11:00", "user",
          "Alice confirmed: her Q3 focus will be auth-flow tracing. First "
          "milestone by end of July."),
    _turn(12, 6, "2026-06-19", "16:00", "user",
          "Quick check: the 30-day decommission reminder Bob set on the "
          "shared CI runner — did that fire?"),
    _turn(12, 7, "2026-06-19", "16:05", "user",
          "Yes. Shared runner decommissioned today. Clean cut, no fallback "
          "needed."),
)


# =========================================================================
# Week 10 (Jun 22-26): Q3 planning
# =========================================================================

SESSION_13: tuple[Doc, ...] = (
    _turn(13, 1, "2026-06-22", "09:30", "user",
          "Q3 planning kickoff today. Carol presenting priorities."),
    _turn(13, 2, "2026-06-22", "10:00", "user",
          "Three pillars: (1) passkey adoption push (Carol), (2) auth-flow "
          "tracing (Alice), (3) session-sharing API (Dave)."),
    _turn(13, 3, "2026-06-23", "14:00", "user",
          "Dave's session-sharing API: intent is to let teams share login "
          "state across sub-accounts. New feature, no legacy constraints."),
    _turn(13, 4, "2026-06-24", "11:00", "user",
          "Eve joining the design review for session-sharing UX tomorrow."),
    _turn(13, 5, "2026-06-25", "10:00", "user",
          "Design review went well. Eve's approach: visual toggles per "
          "sub-account, with an explicit 'share' action."),
    _turn(13, 6, "2026-06-25", "15:00", "user",
          "Bob from infra flagged a concern: session-sharing at high "
          "traffic could triple our Redis load. We'll need capacity "
          "planning."),
    _turn(13, 7, "2026-06-26", "09:00", "user",
          "Q3 approved. Dave starts session-sharing implementation next week."),
)


# =========================================================================
# Week 11 (Jun 29 - Jul 3): Security audit
# =========================================================================

SESSION_14: tuple[Doc, ...] = (
    _turn(14, 1, "2026-06-29", "09:00", "user",
          "External security audit starts today. Alice is our primary "
          "liaison — her platform role + auth background makes her perfect."),
    _turn(14, 2, "2026-06-30", "11:00", "user",
          "Auditors asked about the race-condition fix from April. Alice "
          "walked them through the mutex in RefreshService.js."),
    _turn(14, 3, "2026-07-01", "14:00", "user",
          "Auditors raised a new concern: the passkey keychain-sync we "
          "chose — are there any replay-attack vectors?"),
    _turn(14, 4, "2026-07-01", "14:05", "assistant",
          "WebAuthn has anti-replay built into the challenge-response, but "
          "worth explicitly documenting the sync layer's behavior."),
    _turn(14, 5, "2026-07-02", "10:00", "user",
          "Alice drafted the replay-attack analysis. Clean. Auditors "
          "satisfied."),
    _turn(14, 6, "2026-07-03", "15:00", "user",
          "Audit closes with one medium finding: we should rotate our "
          "signing keys more frequently. Platform team takes the work."),
)


# =========================================================================
# Week 12 (Jul 6-10): Product pivot discussion; retro
# =========================================================================

SESSION_15: tuple[Doc, ...] = (
    _turn(15, 1, "2026-07-06", "10:00", "user",
          "Carol shared a product-pivot idea in this morning's sync: "
          "exploring a social-graph feature on top of our auth platform."),
    _turn(15, 2, "2026-07-06", "10:10", "user",
          "She's framing it as 'low-effort networks' — let users opt-in "
          "to share identity across teams."),
    _turn(15, 3, "2026-07-07", "14:00", "user",
          "Leadership pushback: social features weren't on the Q3 plan. "
          "They want to defer."),
    _turn(15, 4, "2026-07-08", "14:00", "user",
          "Retro today, July 8 as Carol scheduled."),
    _turn(15, 5, "2026-07-08", "14:15", "user",
          "Major discussions in retro: (1) auth-refactor delivery was "
          "smooth, (2) passkey adoption better than expected — already at "
          "40% opt-in, (3) CI migration successfully removed infra bottleneck."),
    _turn(15, 6, "2026-07-08", "14:30", "user",
          "Open issues raised at retro: export-csv flaky test still unresolved "
          "since May. Frank still needs help. Also Bob's Redis capacity "
          "concern for session-sharing needs a plan."),
    _turn(15, 7, "2026-07-10", "11:00", "user",
          "Social-graph feature officially deferred. Dave confirmed Q3 "
          "focus stays on session-sharing only."),
)


# =========================================================================
# Week 13 (Jul 13-17): Dave builds session-sharing API; hits a bug
# =========================================================================

SESSION_16: tuple[Doc, ...] = (
    _turn(16, 1, "2026-07-13", "10:00", "user",
          "Dave started session-sharing implementation today."),
    _turn(16, 2, "2026-07-14", "14:00", "user",
          "Dave hit a subtle bug: session tokens leak across sub-accounts "
          "under rapid switching. Similar pattern to the April "
          "race-condition but in a different code path."),
    _turn(16, 3, "2026-07-14", "14:10", "user",
          "Alice chimed in from platform team — her tracing dashboard "
          "actually helped diagnose it quickly. She could see token "
          "reuse across contexts in the trace."),
    _turn(16, 4, "2026-07-15", "10:00", "user",
          "Dave considering two fixes: (a) separate token pool per "
          "sub-account, (b) stricter scope check at every API boundary."),
    _turn(16, 5, "2026-07-15", "10:15", "user",
          "Going with (a) — separate pools. Cleaner isolation. Alice "
          "agrees."),
    _turn(16, 6, "2026-07-17", "15:00", "user",
          "Fix deployed. Traces show clean separation. Alice's dashboard "
          "confirms the issue is resolved."),
)


# =========================================================================
# Week 14 (Jul 20-24): Customer issue; Frank triages
# =========================================================================

SESSION_17: tuple[Doc, ...] = (
    _turn(17, 1, "2026-07-20", "09:00", "user",
          "Customer support escalation overnight: enterprise customer "
          "reports slow auth on Android."),
    _turn(17, 2, "2026-07-20", "09:30", "user",
          "Frank looking into it. His hypothesis: related to the "
          "keychain-sync Android exclusions we put in place in May."),
    _turn(17, 3, "2026-07-21", "11:00", "user",
          "Frank confirms: older Android clients hitting our exclusion "
          "fallback are taking 8-12 seconds to authenticate. Way too slow."),
    _turn(17, 4, "2026-07-22", "14:00", "user",
          "Frank proposes: replace the fallback with FIDO2 for excluded "
          "Android versions. Basically re-introducing the FIDO2 approach "
          "we rejected in May, but scoped to a narrow population."),
    _turn(17, 5, "2026-07-22", "14:10", "assistant",
          "That's a reasonable revisit given the customer data. The "
          "original concern about FIDO2 was consumer UX — enterprise "
          "customers often have hardware keys available."),
    _turn(17, 6, "2026-07-23", "10:00", "user",
          "Approved. Frank will pilot FIDO2 for enterprise Android "
          "exclusions. Consumer flow stays on keychain-sync."),
    _turn(17, 7, "2026-07-24", "16:00", "user",
          "Pilot patch deployed. Customer reports back: auth now under "
          "2 seconds. Issue resolved."),
)


# =========================================================================
# Week 15 (Jul 27-31): Release; Bob infra updates
# =========================================================================

SESSION_18: tuple[Doc, ...] = (
    _turn(18, 1, "2026-07-27", "09:00", "user",
          "Session-sharing API shipping to 10% traffic this week."),
    _turn(18, 2, "2026-07-28", "14:00", "user",
          "Bob provisioned the extra Redis capacity for session-sharing. "
          "5 additional replicas. Cost roughly +$800/month."),
    _turn(18, 3, "2026-07-29", "11:00", "user",
          "10% rollout looks clean. Dave monitoring."),
    _turn(18, 4, "2026-07-30", "10:00", "user",
          "Alice rolled out signing-key rotation from the audit finding. "
          "30-day rotation cadence. Automated."),
    _turn(18, 5, "2026-07-31", "16:00", "user",
          "Session-sharing now 50%. Everything nominal."),
)


# =========================================================================
# Week 16 (Aug 3-7): Q2 retro with recall questions
# =========================================================================

SESSION_19: tuple[Doc, ...] = (
    _turn(19, 1, "2026-08-03", "10:00", "user",
          "Preparing Q2 retro summary. I need to recall a bunch of things "
          "from the last four months."),
    _turn(19, 2, "2026-08-03", "10:10", "user",
          "Who originally flagged the auth race condition back in April? "
          "Was it Alice or someone else?"),
    # Not answered inline — this is one of the queries below.
    _turn(19, 3, "2026-08-04", "14:00", "user",
          "What was the final authentication approach we shipped for the "
          "token-refresh fix? I want to confirm before writing the retro."),
    _turn(19, 4, "2026-08-05", "11:00", "user",
          "The flaky tests from May — are any still open? I remember "
          "export-csv was unresolved at the July retro."),
    _turn(19, 5, "2026-08-06", "10:00", "user",
          "Which team is Alice on now? I keep forgetting — she transferred "
          "from security earlier this year."),
    _turn(19, 6, "2026-08-07", "15:00", "user",
          "Last thing: what was the passkey binding approach we ultimately "
          "chose after all the flips in May?"),
)


# Aggregate: all E7-long turns PLUS weeks 9-16
NEW_TURNS: tuple[Doc, ...] = (
    SESSION_12 + SESSION_13 + SESSION_14
    + SESSION_15 + SESSION_16 + SESSION_17
    + SESSION_18 + SESSION_19
)

ALL_TURNS: tuple[Doc, ...] = tuple(E7_LONG_TURNS) + NEW_TURNS


def all_turns_sorted() -> list[Doc]:
    return sorted(ALL_TURNS, key=lambda d: d.pub_date)
