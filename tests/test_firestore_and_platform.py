from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from simon.firestore_store import FirestoreStore
from simon.models import (
    ArtistLead,
    ClipEvidence,
    ScoutRun,
    TasteBrief,
    TimestampedObservation,
)
from simon.store import SimonStore, create_store
from simon.web import dispatch_http_request


class _FakeSnapshot:
    def __init__(self, doc_id: str, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, bucket: dict, doc_id: str):
        self._bucket = bucket
        self._doc_id = doc_id

    def set(self, payload: dict) -> None:
        self._bucket[self._doc_id] = dict(payload)

    def get(self) -> _FakeSnapshot:
        return _FakeSnapshot(self._doc_id, self._bucket.get(self._doc_id))


class _FakeCollection:
    def __init__(self, bucket: dict):
        self._bucket = bucket

    def document(self, doc_id: str) -> _FakeDocRef:
        return _FakeDocRef(self._bucket, doc_id)

    def stream(self):
        for doc_id, data in self._bucket.items():
            yield _FakeSnapshot(doc_id, data)


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> _FakeCollection:
        bucket = self._collections.setdefault(name, {})
        return _FakeCollection(bucket)


def _sample_run() -> ScoutRun:
    brief = TasteBrief(brief_id="brief_1", prompt="Stripped-back live vocalists")
    lead = ArtistLead(
        lead_id="lead_1",
        stage_name="Test Singer",
        attribution_status="confirmed",
        attribution_notes="Channel matches artist",
        source_links=["https://www.youtube.com/watch?v=abc12345678"],
    )
    obs = TimestampedObservation(
        observation_id="obs_1",
        clip_id="clip_1",
        source_url="https://www.youtube.com/watch?v=abc12345678",
        play_url="https://www.youtube.com/watch?v=abc12345678&t=18s",
        embed_url="https://www.youtube.com/embed/abc12345678?start=18",
        timestamp="0:18",
        seconds=18,
        dimension="phrasing",
        musical_choice="Holds the syllable back behind the acoustic guitar.",
    )
    clip = ClipEvidence(
        clip_id="clip_1",
        lead_id="lead_1",
        stage_name="Test Singer",
        source_url="https://www.youtube.com/watch?v=abc12345678",
        video_id="abc12345678",
        title="Live Session",
        channel="Test Singer",
        recording_context="live",
        recording_context_notes="Single room mic",
        evaluated_model="gemini-4-hydrogen",
        observations=[obs],
    )
    return ScoutRun(
        run_id="run_test_001",
        mode="demo",
        brief=brief,
        artist_leads=[lead],
        clip_evidence=[clip],
        assessments=[],
        shortlist=[],
        trace=[],
        decision_status="completed",
    )


class TestFirestoreAndPlatform(unittest.TestCase):
    def test_firestore_store_runs_and_documents(self) -> None:
        fake_client = _FakeFirestoreClient()
        store = FirestoreStore(project="gemini4nyc26nyc-2203", client=fake_client)
        self.assertEqual(store.backend, "firestore")

        run = _sample_run()
        store.save_run(run)

        fetched = store.get_run("run_test_001")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["run_id"], "run_test_001")

        runs = store.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], "run_test_001")

        obs = store.get_observations_for_run("run_test_001")
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["seconds"], 18)

        saved = store.save_document("dossiers", "artist_1", {"stage_name": "Test Singer", "tags": ["nyc"]})
        self.assertEqual(saved["doc_id"], "artist_1")
        self.assertEqual(store.get_document("dossiers", "artist_1")["tags"], ["nyc"])
        self.assertEqual(len(store.list_documents("dossiers")), 1)

    def test_sqlite_store_native_documents(self) -> None:
        store = SimonStore(":memory:")
        self.assertEqual(store.backend, "sqlite")
        store.save_document("fleet_runs", "fleet_01", {"agent": "staging-simon-discovery-scout", "ok": True})
        doc = store.get_document("fleet_runs", "fleet_01")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["agent"], "staging-simon-discovery-scout")
        self.assertEqual(len(store.list_documents("fleet_runs")), 1)

    def test_create_store_backend_selection(self) -> None:
        with patch.dict(os.environ, {"SIMON_STORE_BACKEND": "sqlite"}, clear=False):
            store = create_store(db_path=":memory:")
            self.assertEqual(store.backend, "sqlite")

        with self.assertRaises(ValueError):
            create_store(backend="invalid-backend")

    def test_platform_healthz_status_and_fleet_persistence(self) -> None:
        fake_client = _FakeFirestoreClient()
        store = FirestoreStore(project="gemini4nyc26nyc-2203", client=fake_client)

        status, _, body = dispatch_http_request(store, "GET", "/healthz")
        self.assertEqual(status, 200)
        health = json.loads(body.decode("utf-8"))
        self.assertTrue(health["ok"])
        self.assertEqual(health["store_backend"], "firestore")

        status, _, body = dispatch_http_request(store, "GET", "/api/status")
        self.assertEqual(status, 200)
        info = json.loads(body.decode("utf-8"))
        self.assertEqual(info["store_backend"], "firestore")

        fleet_req = json.dumps(
            {
                "agent": "staging-simon-discovery-scout",
                "assignments": ["NYC indie soul vocalists"],
                "dry_run": True,
            }
        ).encode("utf-8")
        status, _, body = dispatch_http_request(store, "POST", "/api/fleet/run", fleet_req)
        self.assertEqual(status, 200)
        fleet_resp = json.loads(body.decode("utf-8"))
        self.assertIn("fleet_run_id", fleet_resp)

        status, _, body = dispatch_http_request(store, "GET", "/api/fleet/runs")
        self.assertEqual(status, 200)
        listed = json.loads(body.decode("utf-8"))
        self.assertEqual(len(listed["fleet_runs"]), 1)
        self.assertEqual(listed["fleet_runs"][0]["fleet_run_id"], fleet_resp["fleet_run_id"])
        self.assertIn("run_id", fleet_resp)
        self.assertEqual(len(fleet_resp["agent_run_ids"]), 1)

        arun_id = fleet_resp["agent_run_ids"][0]
        status, _, body = dispatch_http_request(store, "GET", f"/api/agent-runs/{arun_id}")
        self.assertEqual(status, 200)
        arun = json.loads(body.decode("utf-8"))
        self.assertEqual(arun["run_id"], fleet_resp["run_id"])
        self.assertEqual(len(arun["traces"]), 1)

        # Append a trace span
        trace_req = json.dumps(
            {
                "agent_run_id": arun_id,
                "status": "completed",
                "trace": {"kind": "source_query", "summary": "Queried 13 NYC venue calendars"},
                "output": {"leads_found": 5},
            }
        ).encode("utf-8")
        status, _, body = dispatch_http_request(store, "POST", "/api/agent-runs", trace_req)
        self.assertEqual(status, 200)
        updated = json.loads(body.decode("utf-8"))
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(len(updated["traces"]), 2)
        self.assertEqual(updated["output"]["leads_found"], 5)

    def test_seed_and_query_discovery_sources(self) -> None:
        fake_client = _FakeFirestoreClient()
        store = FirestoreStore(project="gemini4nyc26nyc-2203", client=fake_client)

        status, _, body = dispatch_http_request(store, "POST", "/api/sources/seed")
        self.assertEqual(status, 200)
        seeded = json.loads(body.decode("utf-8"))
        self.assertEqual(seeded["seeded_count"], 42)
        self.assertEqual(seeded["collection"], "source_registry")

        status, _, body = dispatch_http_request(
            store, "GET", "/api/sources?city=New+York&channel=diy_venue_calendar"
        )
        self.assertEqual(status, 200)
        filtered = json.loads(body.decode("utf-8"))
        self.assertGreaterEqual(filtered["count"], 10)
        for src in filtered["sources"]:
            self.assertEqual(src["source_channel"], "diy_venue_calendar")

        # Verify agent DB gateway allows reading source_registry
        status, _, body = dispatch_http_request(store, "GET", "/api/db/source_registry?limit=5")
        self.assertEqual(status, 200)
        db_resp = json.loads(body.decode("utf-8"))
        self.assertEqual(db_resp["collection"], "source_registry")
        self.assertEqual(db_resp["count"], 5)


if __name__ == "__main__":
    unittest.main()
