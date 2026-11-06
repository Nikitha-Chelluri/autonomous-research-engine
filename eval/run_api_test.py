"""Quick API smoke test via ASGI TestClient (no separate server)."""

from fastapi.testclient import TestClient

from app.main import app


def main() -> int:
    client = TestClient(app)
    health = client.get("/health")
    print(f"GET /health -> {health.status_code} {health.json()}")

    create = client.post(
        "/research/jobs",
        json={
            "topic": "Integration test CRM competitive landscape 2026",
            "report_type": "competitive_intelligence",
            "focus_entities": ["Salesforce"],
        },
    )
    print(f"POST /research/jobs -> {create.status_code}")
    if create.status_code != 200:
        print(create.text[:500])
        return 1

    job_id = create.json()["id"]
    detail = client.get(f"/research/jobs/{job_id}")
    print(f"GET /research/jobs/{{id}} -> {detail.status_code} status={detail.json().get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
