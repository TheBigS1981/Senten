# PRD: <Feature Name>

> Product Requirements Document — fill this out before starting any non-trivial feature.
> Takes ~10 minutes. Saves hours of misaligned implementation.
> Created: <date> | Author: <name>

---

## Problem Statement

<!-- What problem does this solve? For whom? Why now? -->
<!-- One paragraph. Be specific — "users can't do X" not "UX is bad" -->

---

## Goal

<!-- One sentence: what does success look like? -->
<!-- Make it measurable if possible: "User can complete checkout in under 3 steps" -->

---

## User Stories

<!-- Format: As a <user type>, I want to <action>, so that <outcome> -->
<!-- List the 3-5 most important stories. Not exhaustive. -->

1. As a **<user type>**, I want to **<action>**, so that **<outcome>**.
2. As a **<user type>**, I want to **<action>**, so that **<outcome>**.
3. As a **<user type>**, I want to **<action>**, so that **<outcome>**.

---

## Acceptance Criteria

<!-- These are the Definition of Done for this feature. -->
<!-- Format: Given <context>, when <action>, then <expected result> -->
<!-- Be specific enough that an agent can verify these without asking. -->

- [ ] Given <context>, when <action>, then <result>
- [ ] Given <context>, when <action>, then <result>
- [ ] Given <context>, when <action>, then <result>

---

## Scope

### In scope
<!-- What will be built? -->
- ...

### Out of scope
<!-- Explicitly list what will NOT be built in this iteration. -->
<!-- This is as important as what IS in scope. -->
- ...

### Future considerations
<!-- Things that are out of scope now but should influence the architecture. -->
- ...

---

## UI / Visual Reference

<!-- Attach screenshots, mockups, or Figma links here. -->
<!-- If none exist, describe the UI in enough detail for @designer to work from. -->

**Reference images:** <drag and drop here, or describe>

**Existing patterns to follow:**
<!-- Which existing screens/components should this be consistent with? -->
- ...

**Key UI decisions:**
<!-- Anything specific about layout, interactions, or behavior. -->
- ...

---

## Technical Notes

<!-- Pre-existing knowledge the agent should know before starting. -->
<!-- Not a full spec — just the constraints and gotchas. -->

**Affected modules:** <list>
**New dependencies needed:** <list or NONE>
**Database changes:** <describe or NONE>
**API changes:** <describe or NONE>
**Breaking changes:** YES/NO — <details>
**Performance considerations:** <any known constraints>
**Security considerations:** <auth, permissions, data sensitivity>

---

## Definition of Done

<!-- What must be true for this feature to be considered complete? -->
<!-- This is what the agent checks before triggering /ship -->

- [ ] All acceptance criteria pass
- [ ] Unit tests written for business logic
- [ ] E2E test covers the primary user journey
- [ ] Code review passed (no CRITICAL/HIGH findings)
- [ ] Documentation updated
- [ ] CHANGELOG entry written
- [ ] Manually verified by: <name> on <date>

---

## Open Questions

<!-- Things that need a decision before or during implementation. -->
<!-- The agent should stop and ask if it hits one of these. -->

- [ ] <question> → needs decision from: <person/role>
- [ ] <question> → needs decision from: <person/role>
