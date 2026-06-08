from app.main import create_app


def test_health_check_returns_ok() -> None:
    app = create_app()
    health_route = next(route for route in app.routes if getattr(route, "path", None) == "/health")

    result = health_route.endpoint()

    assert result["status"] == "ok"
    assert result["trace_id"]
    assert "audit_refs" in result
