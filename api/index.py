"""Vercel Python entrypoint.

Vercel's Python runtime imports this module and looks for an ASGI application
named ``app``. The FastAPI instance lives in ``app.main`` so that uvicorn, the
test suite and ``vercel dev`` all run the same application object; this file is
only the adapter the platform needs.

The import is aliased because this module also has to import the ``app``
package by name, and rebinding ``app`` to the FastAPI instance in the same
statement would make that easy to misread.
"""
from app.main import app as _fastapi_app

app = _fastapi_app

__all__ = ["app"]