"""ADK CLI discovery module for the plasma research-group app."""

from agents.flow import build_app

app = build_app()
root_agent = app.root_agent

__all__ = ["app", "root_agent"]
