# Postmortem: Redis Chat Memory Carryover Contaminated Token Attribution

## Summary

An early context-pruning A/B experiment reported a surprising token increase. Follow-up instrumentation showed that the model prompt was dominated by carried-over Redis chat memory, not by the current CodeGen input. The root cause was a Java memory lifecycle bug: when MySQL `chat_history` was empty, `loadChatHistoryToMemory(...)` returned before clearing the Redis-backed `MessageWindowChatMemory`.

The contaminated token result was invalidated, memory isolation was added to the eval harness, the Java bug was fixed, and the benchmark was rerun under isolated conditions.

## Impact

- Pre-#24 token deltas were not valid pruning-effect evidence.
- The sharded pre-isolation run reported `+12.3%` total tokens and `+14.8%` CodeGen tokens, but this was contaminated by Redis memory carryover.
- After isolation, total tokens were effectively flat/slightly lower (`-1.7%`) and CodeGen-stage input decreased by about `18%`.
- The corrected run preserved structural pass@3 at `90.0%`.

## Timeline

1. A pruning A/B run showed a counterintuitive token increase.
2. Eval-side per-run token attribution localized the movement to CodeGen input.
3. Java-side mechanism metrics showed CodeGen requests stayed `1 -> 1`, but prompt size was much larger before isolation.
4. Prompt-composition diagnostics split the prompt into system, memory, and user buckets.
5. The pre-isolation prompt was mostly memory/history: about `89%` of CodeGen prompt chars were carried-over Redis memory.
6. Code inspection found `loadChatHistoryToMemory(...)` skipped `chatMemory.clear()` when MySQL history was empty.
7. Eval preflight was updated to clear both MySQL `chat_history` and Redis chat memory.
8. The Java product bug was fixed by clearing `MessageWindowChatMemory` before the empty-history return.
9. The benchmark was rerun under Redis/MySQL memory isolation.

## Root Cause

The eval harness cleared MySQL `chat_history` before each run, but the Java service also used Redis-backed LangChain4j `MessageWindowChatMemory` keyed by `appId`.

The Java reload path looked like this:

```java
List<ChatHistory> historyList = this.list(queryWrapper);
if (historyList == null || historyList.isEmpty()) {
    return 0;
}
Collections.reverse(historyList);
chatMemory.clear();
```

When MySQL history was empty, the method returned before clearing Redis-backed memory. Since the A/B harness reused the same `appId`, Redis memory could carry previous generated code and review content across runs and across the A -> B arm boundary.

## Fix

Product fix:

```java
List<ChatHistory> historyList = this.list(queryWrapper);
chatMemory.clear();
if (historyList == null || historyList.isEmpty()) {
    return 0;
}
```

Eval hardening:

- clear MySQL `chat_history` before every run;
- clear Redis chat memory before every run through the diagnostics endpoint;
- keep per-run token attribution and mechanism attribution enabled for validation.

## Corrected Result

Isolated sharded rerun:

- `10` multi-file cases
- `3` runs per case
- `5/5` shards completed
- final infra errors: `0`
- suspicious empty generations: `0`
- token cross-check matched both arms

Key results:

- structural pass@3: `90.0% -> 90.0%`
- total tokens: `323,192 -> 317,785` (`-1.7%`)
- CodeGen-stage input: about `-18%`
- CodeGen mechanism: no input increase in all 10 cases

## Lessons

- Eval harnesses need reliability engineering too.
- Token attribution must isolate both metric windows and application memory state.
- Shared chat memory can silently contaminate A/B experiments even when SQL history is cleared.
- Invalidating a contaminated result is a stronger engineering signal than shipping a convenient number.

## Remaining Boundaries

- The benchmark uses structural checks, not full execution-based correctness.
- The sample size is small and directional.
- The pass@1/run-level improvement in the isolated run was observed but not claimed because arm order and time were still confounded.
