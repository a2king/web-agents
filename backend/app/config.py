import os
from datetime import timedelta


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-dev-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "12")))

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://webagent:webagent@127.0.0.1:3306/webagent",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 3600}

    REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    DATA_DIR = os.getenv("DATA_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data")))
    RUNTIME_BACKEND = os.getenv("RUNTIME_BACKEND", "local")  # local | docker
    WORKER_INLINE = _bool("WORKER_INLINE", False)

    LDAP_ENABLED = _bool("LDAP_ENABLED", False)
    LDAP_URI = os.getenv("LDAP_URI", "ldap://127.0.0.1:389")
    LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "dc=example,dc=com")
    LDAP_USER_FILTER = os.getenv("LDAP_USER_FILTER", "(uid={username})")
    LDAP_BIND_DN = os.getenv("LDAP_BIND_DN", "")
    LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PASSWORD", "")

    DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "Admin@123")

    MAX_CONTENT_LENGTH = 512 * 1024 * 1024


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    REDIS_URL = os.getenv("TEST_REDIS_URL", "")
    WORKER_INLINE = True
    JWT_SECRET_KEY = "test-jwt"
    SECRET_KEY = "test-secret"
    DATA_DIR = os.getenv("TEST_DATA_DIR", "/tmp/webagent-test-data")
    RUNTIME_BACKEND = "local"
