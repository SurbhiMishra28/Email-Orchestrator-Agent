"""Vercel Python entrypoint.

Vercel looks for an ASGI application at a fixed set of module paths
(``main.py``, ``app.py``, ``index.py``, ...) in the service root. This project
keeps its code in the ``app`` package, so this shim re-exports the FastAPI
instance under the name Vercel expects. It changes nothing about local runs:
``npm start`` still boots ``app.main:app``.
"""
from app.main import app

__all__ = ["app"]
