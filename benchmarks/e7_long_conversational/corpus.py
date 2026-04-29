"""E7-long corpus: 8 sessions over 8 weeks, ~100 turns total.

Continuation of the E7 auth-refactor storyline into a longer multi-project
timeline. Stresses memory systems at 4-5× the E7 length:
  - Distant pronouns (40-80 turns from antecedent)
  - Preferences that flip multiple times across weeks
  - Entity role changes (Alice: security team -> platform team)
  - Multiple parallel threads (auth / CI / passkeys / retro)
  - Topics raised and never resolved (CI flakiness, one open ticket)

Entities introduced across the 8 sessions:
  Alice    — security team (wk 1-4) -> platform team (wk 5-8); flagged
             auth race condition
  Bob      — infra engineer; investigates CI slowness
  Carol    — PM; kicks off passkey initiative
  Dave     — inherits auth work from Alice at week 4
  Eve      — designer; contributes to passkey UX wk 3+
  Frank    — ops engineer; mentioned in retro re flaky tests
"""
from __future__ import annotations

from benchmarks.e1_blackboard_stress.corpus import Doc
from benchmarks.e7_conversational.corpus import (
    SESSION_1, SESSION_2, SESSION_3, SESSION_4,
)


def _turn(
    session: int, turn: int, date: str, hour_min: str, speaker: str, text: str,
) -> Doc:
    return Doc(
        id=f"s{session:02d}_t{turn:02d}",
        pub_date=f"{date}T{hour_min}:00",
        text=f"[{speaker}] {text}",
        entities=tuple(),
    )


# =========================================================================
# Weeks 1 (reused from E7: sessions 1-4, Apr 20-24): auth-refactor arc
# =========================================================================

# Use E7's SESSION_1..4 unchanged.


# =========================================================================
# Week 2 (Apr 27-May 1): CI infrastructure investigation
# =========================================================================

SESSION_5: tuple[Doc, ...] = (
    _turn(5, 1, "2026-04-27", "09:00", "user",
          "The CI slowness from last week — Bob on the infra team looked into it "
          "this morning."),
    _turn(5, 2, "2026-04-27", "09:03", "user",
          "Bob says it's disk I/O contention on the shared runner. He's "
          "proposing we move to dedicated runners for our pipeline."),
    _turn(5, 3, "2026-04-27", "09:05", "assistant",
          "Dedicated runners would eliminate the contention. Expected cost "
          "increase is roughly 20-30% per month."),
    _turn(5, 4, "2026-04-27", "09:12", "user",
          "Acceptable tradeoff. Let's do it. I'll tell Bob to go ahead."),
    _turn(5, 5, "2026-04-28", "14:30", "user",
          "Bob started the migration to dedicated runners this afternoon. "
          "Full rollout expected by end of week."),
    _turn(5, 6, "2026-04-30", "10:00", "user",
          "Bob asking: should we keep the shared runner as a fallback? "
          "Costs ~$50/month but no usage."),
    _turn(5, 7, "2026-04-30", "10:02", "assistant",
          "I'd keep it for 30 days then decommission if no fallback was "
          "needed."),
    _turn(5, 8, "2026-04-30", "10:05", "user",
          "Good plan. Tell him to set a calendar reminder."),
    _turn(5, 9, "2026-05-01", "16:00", "user",
          "Dedicated runners live. Pipeline time down from 18 min to about "
          "9 min. Not as fast as the historical 4 min but acceptable."),
    _turn(5, 10, "2026-05-01", "16:05", "user",
          "Some flaky tests still. Frank from ops wants to triage those "
          "next week."),
)


# =========================================================================
# Week 3 (May 4-8): Passkey initiative (Carol kicks off)
# =========================================================================

SESSION_6: tuple[Doc, ...] = (
    _turn(6, 1, "2026-05-04", "10:00", "user",
          "Carol, our PM, wants to explore moving from OAuth to passkeys."),
    _turn(6, 2, "2026-05-04", "10:02", "user",
          "Her argument: passkeys are phishing-resistant and WebAuthn is "
          "mature enough now."),
    _turn(6, 3, "2026-05-04", "10:10", "assistant",
          "Passkeys are a meaningful security upgrade. Main migration risk: "
          "users without a compatible authenticator lose access."),
    _turn(6, 4, "2026-05-04", "10:15", "user",
          "She's proposing a 6-month phase-out of OAuth. Both running in "
          "parallel."),
    _turn(6, 5, "2026-05-05", "11:00", "user",
          "Eve from design is drafting the passkey enrollment UX. She's "
          "asking whether we want phone-binding for the first release."),
    _turn(6, 6, "2026-05-05", "11:05", "user",
          "Let's go with phone-binding via keychain sync. Feels more secure."),
    _turn(6, 7, "2026-05-07", "14:00", "user",
          "Team decision today: passkey rollout approved. 6-month phase-out "
          "of OAuth as Carol proposed."),
    _turn(6, 8, "2026-05-07", "14:30", "user",
          "Also: Alice will be moving to the platform team starting next "
          "week. She'll be handing off the auth race-condition work to Dave."),
    _turn(6, 9, "2026-05-07", "14:35", "assistant",
          "Good that the handoff happens before passkey work starts in "
          "earnest. Dave will need full context on the mutex implementation "
          "Alice designed."),
    _turn(6, 10, "2026-05-08", "09:00", "user",
          "Handoff meeting scheduled for Monday. Alice will walk Dave "
          "through RefreshService.js line 142 and the mutex logic."),
)


# =========================================================================
# Week 4 (May 11-15): Alice transfers; Dave takes over auth
# =========================================================================

SESSION_7: tuple[Doc, ...] = (
    _turn(7, 1, "2026-05-11", "09:30", "user",
          "Alice did the handoff with Dave this morning. She's officially on "
          "the platform team starting today. Her new focus is observability."),
    _turn(7, 2, "2026-05-11", "10:00", "user",
          "Dave is caught up on the mutex work. He's ready to start on "
          "passkey integration."),
    _turn(7, 3, "2026-05-13", "11:00", "user",
          "Dave asks: the mutex Alice implemented — is it still the final "
          "approach, or do we want to revisit with passkeys coming?"),
    _turn(7, 4, "2026-05-13", "11:05", "assistant",
          "The mutex addresses the race condition in token refresh, which "
          "is orthogonal to OAuth vs passkey. It should stay."),
    _turn(7, 5, "2026-05-13", "11:08", "user",
          "Agreed. Mutex stays. Passkey work proceeds separately."),
    _turn(7, 6, "2026-05-15", "15:00", "user",
          "Alice pinged from her new team. She's seeing unusual latency on "
          "the auth observability dashboard she built this week. Asked if "
          "we're doing anything unusual."),
    _turn(7, 7, "2026-05-15", "15:05", "user",
          "I told her nothing deployed recently. Could be the dedicated "
          "runners from Bob's migration — they changed the tracing path."),
)


# =========================================================================
# Week 5 (May 18-22): Passkey implementation, preference flips
# =========================================================================

SESSION_8: tuple[Doc, ...] = (
    _turn(8, 1, "2026-05-18", "10:00", "user",
          "Dave started passkey implementation today."),
    _turn(8, 2, "2026-05-19", "14:00", "user",
          "Dave hit a snag. The keychain-sync approach Eve specced has "
          "issues on Android — not all devices support the sync protocol."),
    _turn(8, 3, "2026-05-19", "14:05", "user",
          "We're reconsidering. Thinking about FIDO2 external authenticators "
          "instead of phone keychain."),
    _turn(8, 4, "2026-05-20", "09:00", "user",
          "Switched to FIDO2 yesterday afternoon. Eve updating the designs."),
    _turn(8, 5, "2026-05-21", "16:00", "user",
          "Hmm, FIDO2 hardware keys are not good UX for consumer users. "
          "Most don't have one."),
    _turn(8, 6, "2026-05-22", "10:00", "user",
          "Reverting to keychain-sync. We'll exclude unsupported Android "
          "versions and message users directly."),
    _turn(8, 7, "2026-05-22", "10:05", "assistant",
          "That's the second flip. Final decision: keychain-sync with "
          "Android exclusions?"),
    _turn(8, 8, "2026-05-22", "10:10", "user",
          "Yes. Eve is updating designs and Dave will revert his branch."),
)


# =========================================================================
# Week 6 (May 25-29): CI improvements in production; flaky tests
# =========================================================================

SESSION_9: tuple[Doc, ...] = (
    _turn(9, 1, "2026-05-25", "09:00", "user",
          "Bob reports: dedicated runners stable for 4 weeks now. CI time "
          "now steady at 6 minutes. Not 4 min like historical, but 3× "
          "better than the bad period."),
    _turn(9, 2, "2026-05-26", "10:00", "user",
          "Frank started the flaky-test triage this week. He's identified "
          "3 tests that fail intermittently: login-mfa, export-csv, "
          "share-link."),
    _turn(9, 3, "2026-05-28", "14:00", "user",
          "Frank fixed login-mfa — it was a race on the MFA token. Similar "
          "pattern to Alice's auth race-condition bug actually."),
    _turn(9, 4, "2026-05-28", "14:05", "assistant",
          "Interesting — two race conditions in auth-adjacent code within "
          "two months. Might be worth a broader audit after passkey work "
          "settles."),
    _turn(9, 5, "2026-05-29", "16:00", "user",
          "export-csv and share-link still flaky. Frank's stuck; might "
          "need help next week."),
)


# =========================================================================
# Week 7 (Jun 1-5): Passkey production rollout
# =========================================================================

SESSION_10: tuple[Doc, ...] = (
    _turn(10, 1, "2026-06-01", "09:00", "user",
          "Passkey gradual rollout starts today. 5% of users on Monday."),
    _turn(10, 2, "2026-06-02", "11:00", "user",
          "Small issue surfaced: some iOS users hit an enrollment loop. "
          "Dave investigating."),
    _turn(10, 3, "2026-06-03", "10:00", "user",
          "Dave found it — iOS 17 keychain-sync behaves differently than "
          "iOS 18. Edge case we didn't catch in testing."),
    _turn(10, 4, "2026-06-03", "15:00", "user",
          "Patch deployed. Affected users can re-enroll."),
    _turn(10, 5, "2026-06-05", "16:00", "user",
          "Rollout now at 50%, no new issues. Carol happy."),
)


# =========================================================================
# Week 8 (Jun 8-12): Retro (includes the recall-heavy queries)
# =========================================================================

SESSION_11: tuple[Doc, ...] = (
    _turn(11, 1, "2026-06-08", "10:00", "user",
          "Getting ready for the quarterly retro. Can you help me recall a "
          "few things from the last two months?"),
    _turn(11, 2, "2026-06-08", "10:05", "user",
          "First: what was the original bug Alice flagged back in April?"),
    # Intentionally NOT answered by the user here — systems must answer this
    # from memory (it's one of the E7-long queries below).
    _turn(11, 3, "2026-06-09", "14:00", "user",
          "Next: what was the final decision on the passkey binding approach?"),
    _turn(11, 4, "2026-06-10", "11:00", "user",
          "One open thread I want to make sure we track: what's the status "
          "of the flaky export-csv test? I don't think Frank resolved it."),
    _turn(11, 5, "2026-06-12", "16:00", "user",
          "Last thing: any other items still open I should mention in the "
          "retro?"),
)


ALL_TURNS: tuple[Doc, ...] = (
    SESSION_1 + SESSION_2 + SESSION_3 + SESSION_4
    + SESSION_5 + SESSION_6 + SESSION_7 + SESSION_8
    + SESSION_9 + SESSION_10 + SESSION_11
)


def all_turns_sorted() -> list[Doc]:
    """Chronological order (already sorted by pub_date across sessions)."""
    return sorted(ALL_TURNS, key=lambda d: d.pub_date)
