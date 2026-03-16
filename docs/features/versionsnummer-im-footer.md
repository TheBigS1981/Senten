# Feature: Versionsnummer im Footer

> Created: 2026-02-24 | Status: Done

## Problem Statement
Users need to know which version of the app is running to report issues accurately or verify deployments.

## Goal
Display the app version in the footer so users can see the current version at a glance.

## User Stories
1. As a **user**, I want to **see the current app version in the footer**, so that **I know which version is deployed and can report issues accurately**.
2. As a **developer**, I want the version to include the git commit hash in development mode**, so that **I can verify which code version is running**.

## Acceptance Criteria
- [x] Given the user is on any page, when they look at the footer, then they see the version number displayed (e.g., "v1.0.0")
- [x] Given the app is running in development mode (not a release tag), when they look at the footer, then they see the git commit hash appended (e.g., "v1.0.0 (abc1234)")
- [x] Given the app is running in production mode (on a release tag), when they look at the footer, then they see only the version without the hash

## Scope
### In scope
- Version variable stored in `app/config.py` 
- Git commit hash auto-detected in dev mode (not on release tag)
- Display in footer area of the UI
### Out of scope
- Version auto-detection from git tags for release mode (will use config value)
- Version history or changelog display

## UI / Visual Reference
<!-- Attach screenshots or describe the UI -->
Currently at line 747-749 in index.html:
```
<footer class="footer">
    Senten &copy; {{ current_year }} &middot; Powered by DeepL API
</footer>
```

Should become:
```
<footer class="footer">
    Senten v1.0.0 &copy; {{ current_year }} &middot; Powered by DeepL API
</footer>
```

## Technical Notes
**Affected modules:** 
- `app/config.py` — add VERSION setting
- `templates/index.html` — add version to footer
**New dependencies needed:** NONE
**Database changes:** NONE
**API changes:** NONE
**Breaking changes:** NO

## Decisions Made
- [2026-02-24] Version stored as static variable in `app/config.py`
- [2026-02-24] Version format: `v1.0.0` (with 'v' prefix)
- [2026-02-24] Git commit hash shown in dev mode only (not on release tag)

## Progress Log
<!-- Most recent first -->

## Open Questions
<!-- Things needing human input before proceeding -->
NONE — all questions resolved
