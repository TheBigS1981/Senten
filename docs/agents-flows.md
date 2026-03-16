# Subagent Flows

Load this file when coordinating between agents or deciding which flow applies to the current task.

---

## How Agents Call Each Other

Agents coordinate through structured handoff blocks. When an agent finishes work that requires follow-up, it appends a `## HANDOFF` block. The next agent reads this and knows exactly what to do.

---

## Flow 1: Feature Development

```
User → @plan (think through approach)
     → build (implement)
     → @code-review (review output)
     → @senior-developer (fix CRITICAL/HIGH findings)
     → @frontend (fix frontend findings)
     → build (fix remaining LOW/INFO findings)
```

## Flow 2: Security or Architecture Task

```
User → @senior-developer (design + implement)
     → @code-review (verify the implementation)
     → build (address any remaining findings)
```

## Flow 3: UI Task

```
User → @frontend (implement component)
     → @code-review (review if flagged in handoff)
     → @senior-developer (only if architectural concern surfaces)
```

## Flow 4: Code Review Only

```
User → @code-review (produces report)
     → @senior-developer (CRITICAL + HIGH findings)
     → @frontend (frontend findings)
     → build (@any findings)
```

## Flow 5: Regular Maintenance (weekly/per sprint)

```
@refactoring (dependency audit + safe updates)
     → @senior-developer (major version updates requiring planning)
     → @tester (if refactoring changed tested code)
     → @documentation (if module structure changed)
```

## Flow 6: Feature Completion (before merge)

```
build / @frontend (implement feature)
     → @tester (write missing tests)
     → @code-review (full review)
     → @documentation (document new behavior + update changelog)
     → @senior-developer / @devops (if infrastructure changes needed)
```

### Flow 7: New Project Visual Identity
```
User → @designer (define color, typography, spacing, tokens)
     → @frontend (implement design system)
     → @code-review (verify accessibility + token usage)
```


---

## Parallel Flows

Use parallel flows when two agents can work independently at the same time — no dependency between their outputs. This saves significant time on larger features.

opencode supports parallel subagents via the Task tool. When an agent spawns two subagents in parallel, both run simultaneously and their results are merged before continuing.

### When to use parallel flows

- Two tasks have no shared files or dependencies
- One agent is waiting for external input while another can already start
- Research/planning can happen while scaffolding is already being built

### How to trigger parallel work

In your prompt, explicitly state that tasks should run in parallel:
```
@senior-developer and @frontend work in parallel:
- @senior-developer: design the API contract for /v1/orders
- @frontend: build the OrderCard component (use placeholder data for now)
```

Or use the parallel flow templates below.

---

### Parallel Flow A: Full-Stack Feature (API + UI simultaneously)

Use when backend API and frontend UI have no implementation dependency on each other yet.

```
User → @plan (define API contract + component spec)
     → confirmation
     ↓
     ├── @senior-developer  (implement API endpoints)   ─┐
     └── @frontend          (implement UI components)   ─┤
                                                         ↓
                             @tester (integration tests after both done)
                           → @code-review (full review)
```

**Condition to merge:** Both agents must complete and output a HANDOFF before @tester starts.

---

### Parallel Flow B: Review + Docs simultaneously

Use when a feature is complete and review and documentation can happen at the same time.

```
build / @frontend (feature complete)
     ↓
     ├── @code-review    (review src/)          ─┐
     └── @documentation  (draft docs + CHANGELOG)─┤
                                                  ↓
                          @senior-developer (fix CRITICAL/HIGH findings)
                        → @documentation (finalize CHANGELOG after review)
```

---

### Parallel Flow C: Maintenance (audit + quality simultaneously)

Use during regular maintenance when dependency audit and code quality work are independent.

```
     ├── @refactoring  (dependency audit + safe updates)  ─┐
     └── @tester       (review + improve test coverage)   ─┤
                                                           ↓
                         @senior-developer (major dep updates requiring planning)
                       → @documentation (update docs if structure changed)
```

---

### Parallel Flow D: Security + Performance audit

Use for dedicated audit sessions.

```
     ├── @senior-developer  (security audit: OWASP Top 10 check)  ─┐
     └── @refactoring       (performance + dependency audit)       ─┤
                                                                    ↓
                             @code-review (consolidate findings)
                           → @tester (add tests for identified gaps)
```

---

## Parallel Flow Rules

- **Never** run two agents on the same file simultaneously — last write wins and changes get lost.
- Always define file boundaries before starting parallel work: "Agent A owns `src/api/`, Agent B owns `src/components/`".
- Each parallel agent produces a HANDOFF block. The coordinating agent reads both before continuing.
- If a parallel agent hits a BLOCKER, it stops and reports immediately — the other agent continues.

### Parallel HANDOFF format

When two agents work in parallel, each produces their own HANDOFF, then a merge summary is output:

```
## PARALLEL HANDOFF MERGE
**Agent A (@senior-developer):** DONE / BLOCKED — <summary>
**Agent B (@frontend):** DONE / BLOCKED — <summary>
**Conflicts found:** YES/NO — <details if YES>
**Ready for next step:** YES/NO
**Next step:** <what happens now>
```


---

## Flow 8: Security Audit

Dedicated security audit — completely separate from regular code review. Run before major releases, after significant auth/API changes, or on a regular schedule (e.g. once per quarter).

```
User → /security-audit
     → @security (OWASP Top 10 audit — read-only, full project)
     → Report confirmed by user
     → @senior-developer (CRITICAL + HIGH findings)
     → @devops (infrastructure + config findings)
     → @refactoring (vulnerable dependencies)
     → @tester (add security regression tests)
     → @security (optional re-audit to verify fixes)
```

**Key difference from `@code-review`:**
- `@code-review` checks security *incidentally* during a PR review
- `@security` audits security *systematically* across the entire project using OWASP Top 10
- `@security` is read-only — it never modifies files
- `@security` produces an attack scenario for every CRITICAL/HIGH finding

**When to run:**
- Before every major release
- After significant changes to: authentication, authorization, API endpoints, data handling
- Quarterly as a scheduled audit
- When onboarding a project (run after `/harmonize`)

---

## When to Skip Agents

- Skip `@code-review` for trivial changes (typos, config values, copy changes)
- Skip `@senior-developer` if code-review Overall Risk is LOW or CLEAN
- Skip `@frontend` if there are no frontend-dimension findings
- Skip `@tester` only for changes with no logic (copy, config, style-only)
- Skip `@devops` if no infrastructure, pipeline, or deployment files are touched
- Skip `@documentation` for internal refactoring with no public API surface changes
- Skip `@refactoring` dependency audit if one was run within the last sprint
- Skip `@security` full audit for trivial changes — use `@code-review` for per-PR security checks instead
