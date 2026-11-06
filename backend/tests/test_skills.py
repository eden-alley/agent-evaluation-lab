from test_quality import client, draft_payload


def test_builtin_skill_is_explicitly_not_ready(client):
    rows = client.get("/api/v1/skills").json()["items"]
    design = next(s for s in rows if s["id"] == "dataset-design")
    assert design["active_version"] is None
    assert client.get("/api/v1/skills/dataset-design/content").status_code == 409
    assert client.get("/api/v1/skills?available_only=true").json()["items"] == []


def publish_test_skill(client, content="Offline fixture only. No production methodology."):
    value = client.post("/api/v1/skills/dataset-design/versions", json={"content": content, "change_note": "离线夹具"})
    assert value.status_code == 201, value.text
    version = value.json()
    assert client.get(f"/api/v1/skills/dataset-design/content?version_id={version['id']}").status_code == 409
    response = client.post(f"/api/v1/skills/dataset-design/versions/{version['id']}/publish")
    assert response.status_code == 200, response.text
    return version


def test_skill_publication_and_old_versions_are_immutable(client):
    version = publish_test_skill(client)
    current = client.get("/api/v1/skills/dataset-design/content").json()
    assert current["version"]["id"] == version["id"]
    newer = publish_test_skill(client, "Second offline fixture only.")
    assert newer["version"] == 2
    old = client.get(f"/api/v1/skills/dataset-design/content?version_id={version['id']}").json()
    assert old["version"]["content"] == version["content"]
    assert client.get("/api/v1/skills?available_only=true&query=评测集").json()["items"][0]["id"] == "dataset-design"


def test_generated_draft_binds_published_skill_version(client):
    version = publish_test_skill(client)
    payload = draft_payload(client)
    reference = {"skill_id": "dataset-design", "version_id": version["id"], "content_hash": version["content_hash"]}
    payload["source"]["skills"] = [reference]
    result = client.post("/api/v1/dataset-drafts", json=payload)
    assert result.status_code == 201, result.text
    assert result.json()["payload"]["source"]["skills"] == [reference]
    payload["request_id"] = "invalid-source"
    reference["content_hash"] = "0" * 64
    assert client.post("/api/v1/dataset-drafts", json=payload).status_code == 422


def test_user_can_register_business_skill_without_generated_content(client):
    value = client.post("/api/v1/skills", json={"name": "用户业务方法", "description": "用于用户定义的场景", "kind": "business", "tags": ["业务"]})
    assert value.status_code == 201, value.text
    assert value.json()["origin"] == "user"
    assert value.json()["active_version"] is None
