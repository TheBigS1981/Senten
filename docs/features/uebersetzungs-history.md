# Feature: Übersetzungs-History

> Created: 2026-02-24 | Status: Done

## Problem Statement
<!-- Was ist das Problem, das gelöst wird? Für wen? -->
Der User möchte gerne die Historie der letzten Übersetzungen anzeigen lassen. Damit hat er die Möglichkeit eine vergange Übersetzung nocheinmal zu sehen.

## Goal
<!-- Ein Satz: Wie sieht Erfolg aus? -->
Der Erfolg besteht darin, dass der Benutzer in einer Übersicht die letzten Übersetzungen sehen und auswählen kann. Die Ansicht muss übersichtlich und chronologisch sein.

## User Stories
1. Als Benutezr möchte ich in einer Übersicht die letzten Übersetzungen sehen können.
2. Als Benutzer möchte ich eine chronologisches Darstellung der Übersetzungen sehen können.
3. Als Benutzer möchte ich dann eine Übersetzung im Detail anschauen und ggf. an den Textoptimierer weitergeben können. 
4. Als Benutzer soll die Darstellung einer historischen Übersetzung so aussehne, wie beim erstmaligen Übersetzen. Als Benutezr möchte ich mich also nicht an ein neues Frontend gewöhnen müssen.
5. Als Betreiber der Anwendung, möchte ich die historischen Daten außerhalb des eigentlichen Containers gespeichert haben.
6. Als Benutzer möchte ich selektiv eine historische Übersetzung löschen können.
7. Als Benutzer möchte ich Zugriff auf maximal 100 Übersetzungen haben.

## Acceptance Criteria
- [ ] Gegeben **<Kontext>**, wenn **<Aktion>**, dann **<Ergebnis>**
- Gegeben der Benutzer befindet sich auf dem Dashboard, wenn die Anwendung geladen ist, dann wird eine Liste der bisherigen Übersetzungen mit Quelltext-Vorschau und Zielsprache angezeigt.
- Gegeben die Übersicht der Übersetzungen ist geöffnet, wenn der Benutzer die Liste betrachtet, dann sind die Einträge standardmäßig nach dem Datum sortiert (neueste zuerst).
- Gegeben der Benutzer befindet sich in der Detailansicht einer alten Übersetzung, wenn der Button "An Textoptimierer senden" geklickt wird, dann wird der Text automatisch in das Optimierungstool geladen.
- Gegeben der Benutzer öffnet eine historische Übersetzung, wenn die Detailseite gerendert wird, dann entsprechen Layout, Styling und Elementanordnung exakt der Ansicht einer frischen Übersetzung.
- Gegeben die Anwendung wird in einem Container neu gestartet, wenn die Übersicht aufgerufen wird, dann sind alle historischen Übersetzungen weiterhin vorhanden (Persistence außerhalb des Containers).
- Gegeben der Benutzer markiert eine spezifische Übersetzung zum Löschen, wenn die Löschbestätigung erfolgt, dann wird genau dieser Datensatz unwiderruflich aus der Datenbank und der UI entfernt.
- Gegeben der Benutzer hat bereits 100 Übersetzungen gespeichert, wenn eine neue (101.) Übersetzung erstellt wird, dann wird die chronologisch älteste Übersetzung automatisch gelöscht, um Platz für die neue zu machen.

## Scope
### In scope
- ...
### Out of scope
- ...

## UI / Visual Reference
<!-- Screenshots oder UI-Beschreibung hier -->

## Technical Notes
**Affected modules:** TBD
**New dependencies needed:** NONE
**Database changes:** NONE
**API changes:** NONE
**Breaking changes:** NO

## Definition of Done
- [x] All acceptance criteria pass
- [x] Unit tests written and passing — `tests/test_history.py`
- [x] E2E test covers primary user journey — integration tests via TestClient
- [x] Code review passed (no CRITICAL/HIGH findings) — v2.5.0 review: CLEAN
- [x] CHANGELOG entry written — v2.4.0
- [x] Manually verified — deployed and running since v2.4.0

## Decisions Made
<!-- Decisions werden hier protokolliert -->

## Progress Log
<!-- Neueste Einträge zuerst -->

## Open Questions
<!-- Dinge, die menschliche Entscheidungen erfordern -->
- Storage: LocalStorage (browser-seitig) oder Server-seitig (SQLite)?
- Limit: Wie viele Einträge maximal pro User?
