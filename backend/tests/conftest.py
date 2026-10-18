import os
os.environ["DATABASE_URL"] = "sqlite:///./test_opsflow.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["DISABLE_DEV_SEED"] = "0"
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event
from app.main import app, Base, engine

if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def client():
    with TestClient(app) as c:
        c.post("/api/dev/seed")
        yield c

def token(client, email="admin@opsflow.local", password="Admin123!"):
    response=client.post("/api/auth/login", json={"email":email,"password":password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]

@pytest.fixture
def auth_headers(client):
    return {"Authorization":f"Bearer {token(client)}"}
