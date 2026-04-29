"""E7 corpus: a 4-session multi-day dialog between an engineer and an AI
coding assistant about an auth bug fix.

Exercises the four agent-platform memory axes:
  - Pronoun resolution ("her", "she", "that bug")
  - Cross-session references ("what did we decide yesterday?")
  - Granularity spectrum (broad summary + precise line-number lookup)
  - Preference evolution (user changes mind, then reverts)

Each turn becomes one Doc for ingest. pub_date is a per-session timestamp.
"""
from __future__ import annotations

from benchmarks.e1_blackboard_stress.corpus import Doc


# ---------------------------------------------------------------------------
# Session 1 — Monday: user reports the bug; Alice named; CI slowness mentioned
# ---------------------------------------------------------------------------

SESSION_1_DATE = "2026-04-20"   # Monday
SESSION_2_DATE = "2026-04-21"   # Tuesday
SESSION_3_DATE = "2026-04-22"   # Wednesday
SESSION_4_DATE = "2026-04-24"   # Friday


def _turn(
    session: int, turn: int, date: str, hour_min: str, speaker: str, text: str,
) -> Doc:
    return Doc(
        id=f"s{session:02d}_t{turn:02d}",
        pub_date=f"{date}T{hour_min}:00",
        text=f"[{speaker}] {text}",
        entities=tuple(),  # let extraction systems derive their own
    )


# Session 1 — Monday 09:00-09:30
SESSION_1: tuple[Doc, ...] = (
    _turn(1, 1, SESSION_1_DATE, "09:00", "user",
          "We have a bug in our auth flow. Token refresh fails silently when "
          "the user is logged in across multiple tabs."),
    _turn(1, 2, SESSION_1_DATE, "09:02", "user",
          "Alice from the security team flagged it yesterday evening. She said "
          "it's a race condition in RefreshService.js."),
    _turn(1, 3, SESSION_1_DATE, "09:05", "assistant",
          "A race condition in a token refresh is typical of concurrent-tab "
          "scenarios. Two common fixes: a mutex around the refresh call, or "
          "a shared event queue via BroadcastChannel."),
    _turn(1, 4, SESSION_1_DATE, "09:08", "user",
          "Alice suggested the mutex approach. Let's go with what she said."),
    _turn(1, 5, SESSION_1_DATE, "09:15", "user",
          "Also the CI has been slow today. Our usual 4-minute pipeline is "
          "taking 18 minutes. Not sure if it's related."),
    _turn(1, 6, SESSION_1_DATE, "09:20", "assistant",
          "The CI slowness is likely an infra issue, unrelated to the auth "
          "bug. I'd track it separately."),
    _turn(1, 7, SESSION_1_DATE, "09:25", "user",
          "OK. Priority is the auth bug. Mutex it is — tomorrow."),
)

# Session 2 — Tuesday 10:00-10:30: user changes mind to event-queue, then
# reverts to mutex within session
SESSION_2: tuple[Doc, ...] = (
    _turn(2, 1, SESSION_2_DATE, "10:00", "user",
          "Okay, I'm going to implement the fix we discussed yesterday."),
    _turn(2, 2, SESSION_2_DATE, "10:03", "user",
          "Where exactly did she say the problem was?"),
    _turn(2, 3, SESSION_2_DATE, "10:04", "assistant",
          "In RefreshService.js — specifically the concurrent refresh call "
          "path."),
    _turn(2, 4, SESSION_2_DATE, "10:08", "user",
          "Grepping… found it. Line 142 in RefreshService.js is where the "
          "two calls collide."),
    _turn(2, 5, SESSION_2_DATE, "10:15", "user",
          "Hmm, actually I'm reconsidering. An event-queue via "
          "BroadcastChannel might be cleaner than a mutex. Less lock "
          "contention."),
    _turn(2, 6, SESSION_2_DATE, "10:20", "assistant",
          "BroadcastChannel would work but it adds a new failure mode: "
          "messages dropped across tabs when one closes mid-refresh."),
    _turn(2, 7, SESSION_2_DATE, "10:25", "user",
          "Fair point. Reverting to the mutex approach after all. Alice's "
          "original recommendation stands."),
)

# Session 3 — Wednesday 14:00-14:20: tests + remembering Monday
SESSION_3: tuple[Doc, ...] = (
    _turn(3, 1, SESSION_3_DATE, "14:00", "user",
          "So yesterday I almost went event-queue but reverted. Mutex in "
          "place now. Let's add tests."),
    _turn(3, 2, SESSION_3_DATE, "14:05", "user",
          "Remind me — what was her original concern? The one from Monday."),
    _turn(3, 3, SESSION_3_DATE, "14:06", "assistant",
          "The race condition in RefreshService.js during concurrent-tab "
          "token refresh."),
    _turn(3, 4, SESSION_3_DATE, "14:10", "user",
          "Right. OK — tests should cover two tabs refreshing within ~50ms "
          "of each other."),
    _turn(3, 5, SESSION_3_DATE, "14:15", "user",
          "Done. Two new tests in refresh-service.test.js, both passing."),
)

# Session 4 — Friday 11:00-11:20: deploying + asks multiple recall questions
SESSION_4: tuple[Doc, ...] = (
    _turn(4, 1, SESSION_4_DATE, "11:00", "user",
          "Deploying the auth fix today."),
    _turn(4, 2, SESSION_4_DATE, "11:02", "user",
          "Before I do — want to credit her in the changelog. Who was it "
          "again who originally flagged this?"),
    _turn(4, 3, SESSION_4_DATE, "11:05", "user",
          "And what did I end up choosing — mutex or event-queue?"),
    _turn(4, 4, SESSION_4_DATE, "11:10", "user",
          "One more thing. The CI was slow on Monday. Anything resolved "
          "since then?"),
)


ALL_TURNS: tuple[Doc, ...] = SESSION_1 + SESSION_2 + SESSION_3 + SESSION_4


def all_turns_sorted() -> list[Doc]:
    """Return all turns in chronological order (which they already are)."""
    return sorted(ALL_TURNS, key=lambda d: d.pub_date)
