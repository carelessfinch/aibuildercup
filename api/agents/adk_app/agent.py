"""Compatibility module for ADK deploy commands that import agent.root_agent."""

from agents.flow import build_app

app = build_app()
root_agent = app.root_agent

__all__ = ["app", "root_agent"]
