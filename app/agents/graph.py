"""Backward-compatible exports; canonical graph lives in app.agent.graph."""

from app.agent.graph import agent_graph, build_agent_graph

build_research_graph = build_agent_graph
research_graph = agent_graph

__all__ = ["agent_graph", "build_agent_graph", "build_research_graph", "research_graph"]
