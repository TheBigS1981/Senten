"""Tests for the history service and API endpoints."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHistoryAPI:
    """Test the history API endpoints."""

    def test_get_history_empty(self, client):
        """Test getting history when empty."""
        response = client.get("/api/history")
        assert response.status_code == 200
        data = response.json()
        assert "records" in data
        assert data["records"] == []

    def test_create_history_record(self, client):
        """Test creating a history record via POST."""
        response = client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": "Hello world",
                "target_text": "Hallo Welt",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["source_text"] == "Hello world"
        assert data["target_text"] == "Hallo Welt"
        assert data["operation_type"] == "translate"

    def test_get_history_after_create(self, client):
        """Test that history returns created records."""
        # Create a record
        client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": "Test text",
                "target_text": "Testergebnis",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )

        response = client.get("/api/history")
        assert response.status_code == 200
        data = response.json()
        assert len(data["records"]) >= 1
        assert data["records"][0]["source_text"] == "Test text"

    def test_translate_does_not_auto_save(self, client):
        """Test that translation does NOT automatically save to history."""
        # First do a translation
        response = client.post(
            "/api/translate", json={"text": "Hello world", "target_lang": "DE"}
        )
        assert response.status_code == 200

        # History should be empty (translate doesn't auto-save anymore)
        response = client.get("/api/history")
        data = response.json()
        assert len(data["records"]) == 0

    def test_write_does_not_auto_save(self, client):
        """Test that write does NOT automatically save to history."""
        response = client.post(
            "/api/write", json={"text": "Make this better", "target_lang": "DE"}
        )
        assert response.status_code == 200

        # History should be empty (write doesn't auto-save anymore)
        response = client.get("/api/history")
        data = response.json()
        assert len(data["records"]) == 0

    def test_get_single_history_record(self, client):
        """Test getting a single history record."""
        # Create a record
        response = client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": "Test",
                "target_text": "Tester",
                "source_lang": "EN",
                "target_lang": "FR",
            },
        )
        record_id = response.json()["id"]

        # Get single record
        response = client.get(f"/api/history/{record_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["source_text"] == "Test"

    def test_get_single_record_not_found(self, client):
        """Test getting non-existent record returns 404."""
        response = client.get("/api/history/99999")
        assert response.status_code == 404

    def test_delete_single_record(self, client):
        """Test deleting a single history record."""
        # Create a record
        response = client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": "To delete",
                "target_text": "Zu löschen",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )
        record_id = response.json()["id"]

        # Delete it
        response = client.delete(f"/api/history/{record_id}")
        assert response.status_code == 200

        # Verify it's gone
        response = client.get(f"/api/history/{record_id}")
        assert response.status_code == 404

    def test_delete_non_existent_record(self, client):
        """Test deleting non-existent record returns 404."""
        response = client.delete("/api/history/99999")
        assert response.status_code == 404

    def test_delete_all_history(self, client):
        """Test deleting all history."""
        # Create some records
        client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": "One",
                "target_text": "Eins",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )
        client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": "Two",
                "target_text": "Zwei",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )

        # Delete all
        response = client.delete("/api/history")
        assert response.status_code == 200
        data = response.json()
        assert "Deleted 2 records" in data["message"]

        # Verify all gone
        response = client.get("/api/history")
        assert len(response.json()["records"]) == 0

    def test_history_pagination(self, client):
        """Test history pagination with limit and offset."""
        # Create multiple records
        for i in range(5):
            client.post(
                "/api/history",
                json={
                    "operation_type": "translate",
                    "source_text": f"Text {i}",
                    "target_text": f"Ergebnis {i}",
                    "source_lang": "EN",
                    "target_lang": "DE",
                },
            )

        # Test limit
        response = client.get("/api/history?limit=2")
        data = response.json()
        assert len(data["records"]) == 2
        assert data["limit"] == 2

        # Test offset
        response = client.get("/api/history?limit=2&offset=2")
        data = response.json()
        assert len(data["records"]) == 2


class TestHistoryDeduplication:
    """Test server-side deduplication of history records."""

    def test_duplicate_within_60_seconds_is_suppressed(self, client):
        """Gleicher Eintrag innerhalb von 60 Sek. darf nicht doppelt gespeichert werden.

        Bug D fix: Verhindert doppelte Einträge bei Page-Reload (sessionStorage geleert)
        oder Frontend-Race-Conditions.
        """
        payload = {
            "operation_type": "translate",
            "source_text": "Dedup test unique text 12345",
            "target_text": "Dedup Test Ergebnis",
            "source_lang": "EN",
            "target_lang": "DE",
        }
        r1 = client.post("/api/history", json=payload)
        r2 = client.post("/api/history", json=payload)

        assert r1.status_code == 201
        assert r2.status_code == 200  # Dedup: 200 statt 201, kein neuer Eintrag

        entries = client.get("/api/history").json()["records"]
        matching = [
            e
            for e in entries
            if e["source_text"] == "Dedup test unique text 12345"
            and e["target_lang"] == "DE"
        ]
        assert len(matching) == 1, (
            f"Erwartet 1 Eintrag nach Dedup, gefunden: {len(matching)}"
        )

    def test_different_target_lang_is_not_deduplicated(self, client):
        """Gleicher Text mit anderer Zielsprache muss als separater Eintrag gespeichert werden."""
        source = "Different lang test unique text 99999"
        r1 = client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": source,
                "target_text": "Translation DE",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )
        r2 = client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": source,
                "target_text": "Translation FR",
                "source_lang": "EN",
                "target_lang": "FR",
            },
        )
        assert r1.status_code == 201
        assert r2.status_code == 201

        entries = client.get("/api/history").json()["records"]
        matching = [e for e in entries if e["source_text"] == source]
        assert len(matching) == 2, (
            f"Erwartet 2 Einträge (DE + FR), gefunden: {len(matching)}"
        )

    def test_different_operation_type_is_not_deduplicated(self, client):
        """Gleicher Text mit anderem operation_type (translate vs write) bleibt separater Eintrag."""
        source = "Op type test unique text 77777"
        r1 = client.post(
            "/api/history",
            json={
                "operation_type": "translate",
                "source_text": source,
                "target_text": "Translated",
                "source_lang": "EN",
                "target_lang": "DE",
            },
        )
        r2 = client.post(
            "/api/history",
            json={
                "operation_type": "write",
                "source_text": source,
                "target_text": "Optimized",
                "source_lang": None,
                "target_lang": "DE",
            },
        )
        assert r1.status_code == 201
        assert r2.status_code == 201


class TestHistoryLimit:
    """Test the automatic history limit enforcement."""

    def test_history_limit_enforced(self, client):
        """Test that records can be created (limit is 100, we create fewer)."""
        # Just verify we can create multiple records
        for i in range(5):
            client.post(
                "/api/history",
                json={
                    "operation_type": "translate",
                    "source_text": f"Test {i}",
                    "target_text": f"Ergebnis {i}",
                    "source_lang": "EN",
                    "target_lang": "DE",
                },
            )

        # Should have 5 records
        response = client.get("/api/history")
        assert len(response.json()["records"]) == 5
