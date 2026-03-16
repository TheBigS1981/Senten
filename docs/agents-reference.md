# Agent Reference

Load this file when you need to decide which agent to invoke, or when a user asks for examples.

---

## When to Use Which Agent

### Use `build` (default) when:
- Making straightforward code changes within a known pattern
- Fixing bugs that don't require architectural decisions
- Writing utility functions, scripts, or configuration

### Use `plan` (Tab key) when:
- Starting a new feature and thinking through the approach
- Evaluating trade-offs without touching code
- You want a second opinion before committing to an implementation

### Use `@backend-architect` when:
- Designing a new system component or service
- Making decisions about database schema or API contracts
- Addressing CRITICAL or HIGH findings from a code review
- Any security-sensitive change (auth, permissions, secrets, encryption)
- A decision will have system-wide consequences

**Example prompts:**
```
@backend-architect We need to add rate limiting to the API. What's the right approach?
@backend-architect Review the auth middleware for security issues
@backend-architect Design the data model for multi-user session management
@backend-architect FINDING-001 from the code review needs fixing — please handle it
```

### Use `@frontend` when:
- Building or modifying UI components
- Working on responsive layouts, dark mode, or animations
- Managing client-side state or data fetching logic
- Fixing accessibility or styling issues

**Example prompts:**
```
@frontend Create a responsive toolbar with dark mode support
@frontend Refactor the translate panel — it has too many responsibilities
@frontend Fix the accessibility issues in the history modal
@frontend The state is duplicated across multiple event handlers — consolidate it
```

### Use `@tester` when:
- Writing new test suites for existing or new code
- Reviewing and improving test coverage
- Setting up testing infrastructure (pytest fixtures, mocks)
- Code review flags missing or insufficient tests

**Example prompts:**
```
@tester Write unit tests for app/services/deepl_service.py
@tester Add integration tests for the /api/translate endpoint
@tester Review test coverage in app/middleware/auth.py and fill the gaps
@tester Add tests for the new LLM streaming endpoint
```

### Use `@devops` when:
- Setting up or modifying CI/CD pipelines
- Writing or improving Dockerfiles
- Managing environment configuration or secrets
- Planning or executing deployments
- Setting up monitoring or health checks

**Example prompts:**
```
@devops Set up a GitHub Actions pipeline with pytest, security scan, and Docker build
@devops Improve our Dockerfile — it runs as root and uses latest tags
@devops Add health check endpoints to the deployment config
@devops Review our secrets handling across all environments
```

### Use `@documentation` when:
- A feature is complete and needs to be documented
- API endpoints are missing documentation
- A significant architectural decision was made (ADR needed)
- README is outdated or incomplete
- Code review flags missing documentation

**Example prompts:**
```
@documentation Document the new LLM streaming API endpoints
@documentation Write an ADR for our decision to use SQLite
@documentation Update the README — the quick start section is outdated
@documentation Add inline documentation to app/middleware/auth.py
```

### Use `@refactoring` when:
- Running a regular dependency audit (security patches, outdated packages)
- Code quality has degraded and needs cleanup before a new feature
- Tech debt needs to be addressed systematically
- A module is too complex and needs to be broken up

**Example prompts:**
```
@refactoring Run a full dependency audit and apply safe updates
@refactoring The translate router has grown too large — refactor it
@refactoring Find and eliminate duplicated logic across app/services/
@refactoring Check for critical security vulnerabilities in our dependencies
```

### Use `@deep-thinker` when:
- A problem has multiple possible causes and you need structured analysis
- You need to trace a bug to its root cause using mental models
- Complex trade-offs need to be evaluated systematically

**Example prompts:**
```
@deep-thinker Users report intermittent 500 errors — trace the root cause
@deep-thinker Analyze why the session cleanup is not running reliably
@deep-thinker We have three auth modes — help structure the decision for adding OAuth2
```

---

## Versioning Rules

| Change type | Bump |
|-------------|------|
| Breaking API change, major rewrite | **major** |
| New feature, new endpoint | **minor** |
| Bug fix, security patch, dependency update, refactoring, docs | **patch** |
| Internal change only (CI config, tooling, no user-facing impact) | none — skip tagging |

### Skip tagging when:
- Change is CI/CD config only
- Change is documentation or comment only with no API surface change
- Change is a WIP commit not intended for release
- Explicitly told to skip by the user

---

### Use `@security` / `/security-audit` when:
- Vor einem Major Release
- Nach signifikanten Änderungen an Auth, API-Endpunkten oder Datenbankzugriffen
- Als regelmäßiger Audit (quartalsweise empfohlen)

**Example prompts:**
```
/security-audit
@security Full OWASP Top 10 audit before v3.0 release
```

---

### Use `/build-from-screenshot` when:
- You have a design mockup, screenshot, or Figma export to implement
- You want pixel-accurate UI implementation from a visual reference
- Drag the image into the opencode chat, then run the command

**Example:**
```
/build-from-screenshot FEATURE_NAME=translate-toolbar
[attach screenshot]
```

---

### Use `/dod` before `/ship`:
- Verifies all acceptance criteria, tests, docs, and accessibility before shipping
- Run after implementation, before version bump

```
/dod FEATURE_NAME=my-feature
```

---

## Custom Commands

Custom commands are one-click workflows. Type `/` in the opencode TUI to see all available commands.

| Command | Usage | What it does |
|---------|-------|-------------|
| `/feature` | `/feature FEATURE_NAME=my-feature` | Creates feature file, updates STATUS.md, starts Flow 1 |
| `/review` | `/review TARGET=app/middleware/` | Runs full code review, routes findings to correct agents |
| `/maintenance` | `/maintenance` | Dependency audit + safe updates + code quality |
| `/ship` | `/ship FEATURE_NAME=my-feature` | Completes feature: tests → docs → version bump |
| `/dod` | `/dod FEATURE_NAME=my-feature` | Checks Definition of Done before shipping |
| `/status` | `/status` | Shows current project state from STATUS.md |
| `/build-from-screenshot` | `/build-from-screenshot` + attach image | Implement UI from visual reference |
| `/security-audit` | `/security-audit` | Full OWASP Top 10 audit — read-only, full project |

### Typical daily workflow using commands

```
Morning:
  /status                          ← see where things stand

Starting new work:
  /feature FEATURE_NAME=llm-streaming   ← sets everything up

During development:
  @frontend, @backend-architect, build  ← normal agent work
  /build-from-screenshot           ← when implementing from a mockup

Before merging:
  /dod FEATURE_NAME=llm-streaming       ← verify Definition of Done
  /ship FEATURE_NAME=llm-streaming      ← completes the full cycle

Weekly:
  /maintenance                     ← dependency audit + quality pass

Quarterly:
  /security-audit                  ← OWASP Top 10 audit
```

---

## Parallel Work

For larger features, agents can work simultaneously. Add this to your prompt to trigger parallel execution:

```
Work in parallel:
- @backend-architect: <task A — owns app/routers/>
- @frontend: <task B — owns static/js/>
```

See `docs/agents-flows.md` for the four parallel flow templates (Full-Stack, Review+Docs, Maintenance, Security+Performance).

**Key rule:** Always define which files each agent owns before starting parallel work.

