import json
from unittest.mock import MagicMock, patch

from app.api.health_routes import health, readiness


def test_health_returns_ok_status():
    response = health()

    assert response["status"] == "ok"
    assert response["app"]
    assert response["version"]


def test_ready_returns_200_when_database_is_up():
    with patch("app.api.health_routes.engine") as engine:
        engine.connect.return_value.__enter__ = MagicMock()
        engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        response = readiness()

    assert response.status_code == 200
    assert json.loads(response.body)["database"] == "connected"


def test_ready_returns_503_when_database_is_down():
    """Kubernetes only stops routing traffic if the probe returns a non-2xx status."""
    with patch("app.api.health_routes.engine") as engine:
        engine.connect.side_effect = RuntimeError("db down")
        response = readiness()

    assert response.status_code == 503
    assert json.loads(response.body)["status"] == "degraded"
