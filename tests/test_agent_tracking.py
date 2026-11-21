"""Live agent lifecycle events reach connected dashboard clients."""
from app.agents import CalendarAgent


def test_every_agent_is_instrumented(client):
    """Every subagent publishes start/completion events over the websocket."""
    import inspect

    import app.agents as agents_module

    instrumented = {
        name
        for name, obj in vars(agents_module).items()
        if inspect.isclass(obj)
        and obj.__module__ == "app.agents"
        and getattr(obj, "__name__", "").endswith(
            ("Agent", "Manager", "Responder")
        )
    }
    assert "EmailAgent" in instrumented
    assert "QueueManager" in instrumented
    assert "AutoResponder" in instrumented
    assert len(instrumented) >= 8


def test_calendar_agent_events_stream_over_websocket(client):
    with client.websocket_connect("/ws/live-logs") as websocket:
        CalendarAgent().available()
        events = [websocket.receive_json() for _ in range(4)]

    assert [(e["scope"], e["status"]) for e in events] == [
        ("agent", "started"),
        ("method", "started"),
        ("method", "completed"),
        ("agent", "completed"),
    ]
    assert all(e["agent"] == "CalendarAgent" for e in events)
    assert all(e["method"] == "available" for e in events)


def test_ai_brain_agent_events_stream_over_websocket(client):
    from app.agents import AIBrainAgent

    with client.websocket_connect("/ws/live-logs") as websocket:
        AIBrainAgent().enhance_subject("hello", {"business_name": "Acme"})
        events = [websocket.receive_json() for _ in range(4)]

    assert all(e["agent"] == "AIBrainAgent" for e in events)
    assert events[1]["method"] == "enhance_subject"
    assert events[-1]["status"] == "completed"


def test_agent_method_failure_emits_failed_status(client):
    """A method that raises must report 'failed', not 'completed'."""
    from app.live_logs import _instrument_method

    class Boom(Exception):
        pass

    def explode(*_args, **_kwargs):
        raise Boom("nope")

    wrapped = _instrument_method("ProbeAgent", "explode", explode)

    with client.websocket_connect("/ws/live-logs") as websocket:
        try:
            wrapped()
        except Boom:
            pass
        events = [websocket.receive_json() for _ in range(4)]

    assert events[1]["status"] == "started"
    assert events[2]["status"] == "failed"


def test_returned_failure_is_reported_as_failed(client):
    """Agents signal failure with (False, reason); tracking must reflect that."""
    from app.agents import SenderAgent

    class FakeConfig:
        host = "smtp.example.com"
        port = 587
        user = "u"
        password = "p"
        sender = "s@example.com"

    agent = SenderAgent.__new__(SenderAgent)
    agent.smtp_config = FakeConfig()

    with client.websocket_connect("/ws/live-logs") as websocket:
        ok, message = SenderAgent.validate_configuration(agent)
        events = [websocket.receive_json() for _ in range(4)]

    if ok:
        assert events[2]["status"] == "completed"
    else:
        assert events[2]["status"] == "failed", message
