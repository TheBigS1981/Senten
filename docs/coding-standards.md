# Coding Standards

Load this file when writing or reviewing code, or when a user asks about project conventions.

These standards apply across all languages and frameworks used in this project.

---

## Structure & Readability

- One file, one responsibility. If a file needs a long comment to explain its purpose, it is too large.
- Functions do exactly one thing. ~40 lines is the guideline — not a hard rule, but a signal.
- Naming: descriptive verbs and nouns. No cryptic abbreviations.
- No commented-out code in commits. No `TODO` without an issue reference.

## Scope

- Do not refactor, rename, or restructure code unrelated to the current task unless explicitly asked.
- Stay within the boundaries of the files and modules relevant to the task. If adjacent code looks problematic, flag it in the handoff — do not fix it silently.

## Error Handling

- Error paths are as important as the happy path. Both get implemented.
- No silent errors (`catch (e) {}`). Errors are logged or propagated — never swallowed.
- All external calls (APIs, DB, filesystem) have timeouts and error handling.

## Security (always)

- No secrets in code. No credentials in comments.
- User input is always validated and sanitized at the system boundary.
- Parameterized queries only. Never string concatenation for SQL or shell commands.

## Dependencies

- No new dependency without naming the trade-off (size, maintenance, license).
- Use existing patterns in the project before introducing new ones.

## Tests

- New logic gets tests. No "I'll test this later."
- Tests verify behavior, not implementation details.

---

## Conventional Commits

Every commit message must follow the Conventional Commits standard. This enables automatic changelog generation and makes git history scannable.

### Format

```
<type>(<scope>): <short description>

[optional body]

[optional footer]
```

### Types

| Type | When to use |
|------|-------------|
| `feat` | A new feature visible to users |
| `fix` | A bug fix |
| `chore` | Build, tooling, dependency updates — no production code change |
| `refactor` | Code restructuring without behavior change |
| `test` | Adding or fixing tests |
| `docs` | Documentation only |
| `style` | Formatting, whitespace — no logic change |
| `perf` | Performance improvement |
| `ci` | CI/CD pipeline changes |
| `revert` | Reverting a previous commit |

### Scope (optional but recommended)

Use the module or area affected: `auth`, `api`, `ui`, `db`, `payments`, `cart`, etc.

### Rules

- Description is lowercase, imperative mood, no period at the end
- `feat` and `fix` always trigger a CHANGELOG entry
- Breaking changes: add `!` after type/scope → `feat(api)!: remove v1 endpoints`
  - AND add footer: `BREAKING CHANGE: <description>`
- Max 72 characters for the subject line
- Body explains *why*, not *what*

### Examples

```
feat(auth): add OAuth2 login with GitHub
fix(cart): prevent duplicate items on rapid clicks
chore(deps): update express from 4.18 to 4.19
refactor(orders): extract order validation into service
docs(api): document /v1/payments endpoints
test(auth): add unit tests for token refresh logic
feat(billing)!: replace Stripe v1 with Stripe v2 SDK

BREAKING CHANGE: webhook payload format has changed, update all listeners
```

### Changelog mapping

| Commit type | Changelog section |
|-------------|------------------|
| `feat` | `### Added` |
| `fix` | `### Fixed` |
| `perf` | `### Changed` |
| `refactor` (public API) | `### Changed` |
| `feat!` / `fix!` | `### Breaking Changes` |
| `chore`, `test`, `ci`, `style` | not in changelog |
