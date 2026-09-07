import os
import shutil
import tempfile

import pytest

os.environ["WORKER_INLINE"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture()
def app():
    from app import create_test_app
    from app.config import TestConfig

    data_dir = tempfile.mkdtemp(prefix="webagent-")
    TestConfig.DATA_DIR = data_dir
    application = create_test_app()
    application.config["DATA_DIR"] = data_dir
    application.runtime.root = __import__("pathlib").Path(data_dir)
    yield application
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
    token = resp.get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}
