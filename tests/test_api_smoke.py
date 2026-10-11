"""Smoke tests for the preprocess FastAPI service.

Redis and Celery are replaced with in-memory fakes, so no broker is needed.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

HEADERS = {"X-API-KEY": "test-api-key"}


@pytest.fixture
def client():
    from app import main
    from conftest import FAKE_REPOSITORY

    FAKE_REPOSITORY.items.clear()
    task = MagicMock()
    with patch.object(main, "preprocess_task", task):
        with TestClient(main.app) as c:
            c.repo = FAKE_REPOSITORY
            c.task = task
            yield c


def test_health_reports_healthy(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["service"] == "service-trocr-preprocess"
    assert body["redis"] == "connected"


def test_status_requires_api_key(client):
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"X-API-KEY": "wrong"}).status_code == 401


def test_status_empty_list(client):
    r = client.get("/status", headers=HEADERS)
    assert r.status_code == 200
    assert r.json() == []


def test_unknown_job_is_404(client):
    r = client.get("/status/does-not-exist", headers=HEADERS)
    assert r.status_code == 404


def test_zip_job_is_created_and_dispatched(client):
    r = client.post(
        "/preprocess/zip",
        headers=HEADERS,
        json={
            "zip_url": "https://example.com/export.zip",
            "huggingface_target_repo_name": "org/target",
        },
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["request_id"]
    client.task.apply_async.assert_called_once()
    assert client.task.apply_async.call_args.kwargs["task_id"] == job["request_id"]

    fetched = client.get(f"/status/{job['request_id']}", headers=HEADERS)
    assert fetched.status_code == 200
    assert fetched.json()["request_id"] == job["request_id"]
    assert len(client.get("/status", headers=HEADERS).json()) == 1


def test_hf_job_is_created_and_token_not_echoed(client):
    r = client.post(
        "/preprocess/hf",
        headers=HEADERS,
        json={
            "huggingface_source_repo_name": "org/raw-xml",
            "huggingface_target_repo_name": "org/target",
            "huggingface_token": "hf_secret_token_value",
        },
    )
    assert r.status_code == 201, r.text
    assert "hf_secret_token_value" not in r.text
    kwargs = client.task.apply_async.call_args.kwargs["kwargs"]
    assert kwargs["huggingface_token"] == "hf_secret_token_value"
    assert "huggingface_token" not in kwargs["status_dict"]


def test_invalid_zip_url_is_rejected(client):
    r = client.post("/preprocess/zip", headers=HEADERS, json={"zip_url": "not-a-url"})
    assert r.status_code == 422
