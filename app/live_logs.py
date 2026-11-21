"""Transient agent lifecycle event broadcasting for connected dashboard clients."""
import asyncio
import inspect
import logging
import threading
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

logger = logging.getLogger(__name__)


class LiveLogManager:
    """Broadcast high-level agent method events without persisting them."""

    def __init__(self):
        self._subscribers = {}
        self._lock = threading.Lock()

    def subscribe(self):
        queue = asyncio.Queue()
        with self._lock:
            self._subscribers[queue] = asyncio.get_running_loop()
        return queue

    def unsubscribe(self, queue):
        with self._lock:
            self._subscribers.pop(queue, None)

    def publish(self, event):
        with self._lock:
            subscribers = tuple(self._subscribers.items())
        for queue, loop in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError as exc:
                logger.warning("Could not deliver live agent log: %s", exc)


live_logs = LiveLogManager()


def _publish_agent_event(agent, method, status, scope):
    live_logs.publish(
        {
            "id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "method": method,
            "scope": scope,
            "status": status,
            "message": f"{agent} {status}" if scope == "agent" else f"{agent}.{method} {status}",
        }
    )


def _publish_method_start(agent_name, method_name):
    _publish_agent_event(agent_name, method_name, "started", "agent")
    _publish_agent_event(agent_name, method_name, "started", "method")


def _publish_method_end(agent_name, method_name, status):
    _publish_agent_event(agent_name, method_name, status, "method")
    _publish_agent_event(agent_name, method_name, status, "agent")


def _outcome(result):
    """Map an agent method's return value to a lifecycle status.

    Several agents report failure by returning ``(False, reason)`` instead of
    raising, so checking only for exceptions would log a failed send as
    "completed". ``(True, ...)`` and plain values mean success.
    """
    if isinstance(result, tuple) and result and isinstance(result[0], bool):
        return "completed" if result[0] else "failed"
    if isinstance(result, dict) and "success" in result:
        return "completed" if result["success"] else "failed"
    return "completed"


def _instrument_method(agent_name, method_name, method):
    if inspect.iscoroutinefunction(method):
        @wraps(method)
        async def async_wrapper(*args, **kwargs):
            _publish_method_start(agent_name, method_name)
            try:
                result = await method(*args, **kwargs)
            except Exception:
                _publish_method_end(agent_name, method_name, "failed")
                raise
            _publish_method_end(agent_name, method_name, _outcome(result))
            return result

        return async_wrapper

    @wraps(method)
    def sync_wrapper(*args, **kwargs):
        _publish_method_start(agent_name, method_name)
        try:
            result = method(*args, **kwargs)
        except Exception:
            _publish_method_end(agent_name, method_name, "failed")
            raise
        _publish_method_end(agent_name, method_name, _outcome(result))
        return result

    return sync_wrapper


def instrument_agent(agent_class):
    """Add start/completion events to each public method on an agent."""
    for name, method in vars(agent_class).items():
        if not name.startswith("_") and inspect.isfunction(method):
            setattr(agent_class, name, _instrument_method(agent_class.__name__, name, method))
    return agent_class
