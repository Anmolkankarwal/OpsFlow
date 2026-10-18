from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from fastapi.testclient import TestClient
from app.main import SessionLocal, User
from conftest import token

def headers(tok): return {"Authorization":f"Bearer {tok}"}

def test_login_and_team_scoped_authorization(client):
    member=token(client,"member@opsflow.local","Member123!")
    response=client.get("/api/items",headers=headers(member))
    assert response.status_code==200
    other=token(client,"other@opsflow.local","Other123!")
    item_id=response.json()["items"][0]["id"]
    denied=client.get(f"/api/items/{item_id}",headers=headers(other))
    assert denied.status_code==403

def test_cross_team_user_cannot_write_or_read_item_history(client):
    admin=token(client)
    item=client.get("/api/items",headers=headers(admin)).json()["items"][0]
    other=token(client,"other@opsflow.local","Other123!")
    item_headers=headers(other)
    assert client.patch(f"/api/items/{item['id']}",json={"title":"Unauthorized edit","version":item["version"]},headers=item_headers).status_code==403
    assert client.get(f"/api/items/{item['id']}/activity",headers=item_headers).status_code==403
    assert client.get(f"/api/items/{item['id']}/comments",headers=item_headers).status_code==403
    assert client.post(f"/api/items/{item['id']}/comments",json={"body":"Unauthorized comment"},headers=item_headers).status_code==403

def test_inactive_user_cannot_log_in(client):
    with SessionLocal() as db:
        user=db.query(User).filter_by(email="member@opsflow.local").one()
        user.active=False
        db.commit()
    response=client.post("/api/auth/login",json={"email":"member@opsflow.local","password":"Member123!"})
    assert response.status_code==401

def test_search_and_pagination_are_server_side(client):
    tok=token(client)
    first=client.get("/api/items?page=1&page_size=2",headers=headers(tok))
    second=client.get("/api/items?page=2&page_size=2",headers=headers(tok))
    assert first.status_code==second.status_code==200
    assert first.json()["total"]==4
    assert first.json()["pages"]==2
    assert len(first.json()["items"])==len(second.json()["items"])==2
    assert {item["id"] for item in first.json()["items"]}.isdisjoint({item["id"] for item in second.json()["items"]})
    search=client.get("/api/items?q=payment&page=1&page_size=20",headers=headers(tok))
    assert search.json()["total"]==1
    assert "payment" in search.json()["items"][0]["title"].lower()

def test_item_changes_and_comments_create_activity_events(client):
    tok=token(client)
    item=client.get("/api/items",headers=headers(tok)).json()["items"][0]
    updated=client.patch(f"/api/items/{item['id']}",json={"priority":"High","version":item["version"]},headers=headers(tok))
    assert updated.status_code==200
    comment=client.post(f"/api/items/{item['id']}/comments",json={"body":"Investigating the operational impact."},headers=headers(tok))
    assert comment.status_code==201
    events=client.get(f"/api/items/{item['id']}/activity",headers=headers(tok)).json()
    assert {event["action"] for event in events}>={"priority_changed","updated","comment_added"}
    comments=client.get(f"/api/items/{item['id']}/comments",headers=headers(tok)).json()
    assert comments[-1]["body"]=="Investigating the operational impact."

def test_idempotent_create_returns_same_item(client):
    tok=token(client)
    h={**headers(tok),"Idempotency-Key":"demo-create-key-1"}
    body={"title":"Investigate idempotency","team_id":1,"priority":"High"}
    first=client.post("/api/items",json=body,headers=h)
    second=client.post("/api/items",json=body,headers=h)
    assert first.status_code==201 and second.status_code==201
    assert first.json()["id"]==second.json()["id"]
    assert client.get("/api/items",headers=headers(tok)).json()["total"]==5

def test_create_item_succeeds_with_idempotency_key(client):
    tok=token(client)
    response=client.post("/api/items",json={"title":"Create one work item","team_id":1,"priority":"High"},headers={**headers(tok),"Idempotency-Key":"successful-create-key"})
    assert response.status_code==201, response.text
    item=response.json()
    assert item["title"]=="Create one work item"
    assert item["team_id"]==1
    events=client.get(f"/api/items/{item['id']}/activity",headers=headers(tok))
    assert events.status_code==200
    assert any(event["action"]=="created" for event in events.json())

def test_consecutive_creates_with_distinct_keys_create_distinct_items(client):
    tok=token(client)
    first=client.post("/api/items",json={"title":"First consecutive item","team_id":1},headers={**headers(tok),"Idempotency-Key":"consecutive-create-key-1"})
    second=client.post("/api/items",json={"title":"Second consecutive item","team_id":1},headers={**headers(tok),"Idempotency-Key":"consecutive-create-key-2"})
    assert first.status_code==201, first.text
    assert second.status_code==201, second.text
    assert first.json()["id"]!=second.json()["id"]
    assert client.get("/api/items",headers=headers(tok)).json()["total"]==6

def test_idempotency_key_rejects_a_different_payload(client):
    tok=token(client)
    h={**headers(tok),"Idempotency-Key":"same-key-different-payload"}
    first=client.post("/api/items",json={"title":"Original request","team_id":1},headers=h)
    conflict=client.post("/api/items",json={"title":"Changed request","team_id":1},headers=h)
    assert first.status_code==201
    assert conflict.status_code==409
    assert client.get("/api/items",headers=headers(tok)).json()["total"]==5

def test_stale_update_is_rejected(client):
    tok=token(client)
    item=client.get("/api/items",headers=headers(tok)).json()["items"][0]
    first=client.patch(f"/api/items/{item['id']}",json={"title":"Updated first","version":item["version"]},headers=headers(tok))
    assert first.status_code==200
    stale=client.patch(f"/api/items/{item['id']}",json={"title":"Stale overwrite","version":item["version"]},headers=headers(tok))
    assert stale.status_code==409
    current=client.get(f"/api/items/{item['id']}",headers=headers(tok)).json()
    assert current["title"]=="Updated first"

def test_invalid_workflow_jump_is_rejected(client):
    tok=token(client)
    item=client.get("/api/items",headers=headers(tok)).json()["items"][0]
    response=client.post(f"/api/items/{item['id']}/transition",json={"target_status":"Closed","version":item["version"]},headers=headers(tok))
    assert response.status_code==400

def test_viewer_cannot_modify_and_lead_can_approve(client):
    viewer=token(client,"viewer@opsflow.local","Viewer123!")
    item=client.get("/api/items",headers=headers(viewer)).json()["items"][0]
    denied=client.patch(f"/api/items/{item['id']}",json={"title":"Nope","version":item["version"]},headers=headers(viewer))
    assert denied.status_code==403
    lead=token(client,"lead@opsflow.local","Lead123!")
    approval=next(i for i in client.get("/api/items",headers=headers(lead)).json()["items"] if i["status"]=="Awaiting Approval")
    response=client.post(f"/api/items/{approval['id']}/transition",json={"target_status":"Resolved","version":approval["version"]},headers=headers(lead))
    assert response.status_code==200
    assert response.json()["status"]=="Resolved"
    events=client.get(f"/api/items/{approval['id']}/activity",headers=headers(lead)).json()
    assert events[0]["action"]=="approval_approved"

def test_admin_can_approve_eligible_item(client):
    admin=token(client)
    approval=next(i for i in client.get("/api/items",headers=headers(admin)).json()["items"] if i["status"]=="Awaiting Approval")
    response=client.post(f"/api/items/{approval['id']}/transition",json={"target_status":"Resolved","version":approval["version"]},headers=headers(admin))
    assert response.status_code==200, response.text
    assert response.json()["status"]=="Resolved"
    events=client.get(f"/api/items/{approval['id']}/activity",headers=headers(admin)).json()
    assert events[0]["action"]=="approval_approved"

def test_member_cannot_approve_or_reject_by_direct_transition(client):
    member=token(client,"member@opsflow.local","Member123!")
    item=next(i for i in client.get("/api/items",headers=headers(member)).json()["items"] if i["status"]=="Awaiting Approval")
    for target in ("Resolved","In Progress"):
        denied=client.post(f"/api/items/{item['id']}/transition",json={"target_status":target,"version":item["version"]},headers=headers(member))
        assert denied.status_code==403, denied.text
    current=client.get(f"/api/items/{item['id']}",headers=headers(member)).json()
    assert current["status"]=="Awaiting Approval"
    events=client.get(f"/api/items/{item['id']}/activity",headers=headers(member)).json()
    assert not any(event["action"].startswith("approval_") for event in events)

def test_lead_can_reject_eligible_item_with_audit_event(client):
    lead=token(client,"lead@opsflow.local","Lead123!")
    item=next(i for i in client.get("/api/items",headers=headers(lead)).json()["items"] if i["status"]=="Awaiting Approval")
    response=client.post(f"/api/items/{item['id']}/transition",json={"target_status":"In Progress","version":item["version"]},headers=headers(lead))
    assert response.status_code==200, response.text
    assert response.json()["status"]=="In Progress"
    events=client.get(f"/api/items/{item['id']}/activity",headers=headers(lead)).json()
    assert events[0]["action"]=="approval_rejected"
    assert "returned to In Progress" in events[0]["details"]

def test_approval_decision_is_rejected_when_item_is_not_awaiting_approval(client):
    lead=token(client,"lead@opsflow.local","Lead123!")
    item=next(i for i in client.get("/api/items",headers=headers(lead)).json()["items"] if i["status"]=="Open")
    response=client.post(f"/api/items/{item['id']}/transition",json={"target_status":"Resolved","version":item["version"]},headers=headers(lead))
    assert response.status_code==400

def test_member_cannot_approve_or_see_approval_queue(client):
    member=token(client,"member@opsflow.local","Member123!")
    approval=next(i for i in client.get("/api/items",headers=headers(member)).json()["items"] if i["status"]=="Awaiting Approval")
    queue=client.get("/api/items?awaiting_my_approval=true",headers=headers(member))
    assert queue.status_code==200
    assert queue.json()["total"]==0
    denied=client.post(f"/api/items/{approval['id']}/transition",json={"target_status":"Resolved","version":approval["version"]},headers=headers(member))
    assert denied.status_code==403

def test_claim_only_succeeds_once(client):
    tok=token(client,"member@opsflow.local","Member123!")
    items=client.get("/api/items",headers=headers(tok)).json()["items"]
    unassigned=next(i for i in items if i["assignee_id"] is None)
    first=client.post(f"/api/items/{unassigned['id']}/claim",headers=headers(tok))
    assert first.status_code==200
    # A second member cannot silently take the already claimed item.
    other=token(client,"admin@opsflow.local","Admin123!")
    second=client.post(f"/api/items/{unassigned['id']}/claim",headers=headers(other))
    assert second.status_code==409

def test_concurrent_claims_have_exactly_one_winner(client):
    admin=token(client)
    created=client.post("/api/items",json={"title":"Concurrent claim race","team_id":1},headers={**headers(admin),"Idempotency-Key":"concurrent-claim-create"})
    assert created.status_code==201
    item_id=created.json()["id"]
    member=token(client,"member@opsflow.local","Member123!")
    lead=token(client,"lead@opsflow.local","Lead123!")
    start=Barrier(2)

    def attempt_claim(access_token):
        with TestClient(client.app) as concurrent_client:
            start.wait()
            return concurrent_client.post(f"/api/items/{item_id}/claim",headers=headers(access_token)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt_claim,[member,lead]))
    assert sorted(results)==[200,409]

def test_concurrent_updates_reject_one_stale_version(client):
    access_token=token(client)
    item=client.get("/api/items",headers=headers(access_token)).json()["items"][0]
    start=Barrier(2)

    def attempt_update(title):
        with TestClient(client.app) as concurrent_client:
            start.wait()
            response=concurrent_client.patch(f"/api/items/{item['id']}",json={"title":title,"version":item["version"]},headers=headers(access_token))
            return response.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(attempt_update,["Concurrent update A","Concurrent update B"]))
    assert sorted(results)==[200,409]


def test_dev_seed_can_be_disabled_explicitly(client, monkeypatch):
    monkeypatch.setenv("DISABLE_DEV_SEED", "1")
    response = client.post("/api/dev/seed")
    assert response.status_code == 404


def test_dev_seed_is_disabled_by_default_on_render(client, monkeypatch):
    monkeypatch.delenv("DISABLE_DEV_SEED", raising=False)
    monkeypatch.setenv("RENDER", "true")
    response = client.post("/api/dev/seed")
    assert response.status_code == 404
