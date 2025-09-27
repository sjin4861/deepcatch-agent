# Agent Module Guide

This directory implements the LangGraph-based conversation agent that powers Deepcatch's fishing assistant. It is organized to make the core flow easy to understand while allowing new tools and behaviors to be plugged in without rewriting the graph.

## 📁 Directory structure

```text
server/src/agent/
├── __init__.py
├── agent_requirements.md
├── conversation_models.py
├── conversation_tools.py
├── graph.py
├── nodes.py
├── openai_client.py
├── planner.py
├── services.py
├── tool_results.py
├── toolkit/
│   ├── __init__.py
│   ├── base.py
│   ├── registry.py
│   └── builtins/
│       ├── __init__.py
│       ├── call.py
│       ├── fish.py
│       ├── planner.py
│       └── weather.py
└── types.py
```

## 🔌 High-level architecture

1. **Models & types** (`conversation_models.py`, `types.py`) define the dataclasses and Pydantic models that move through the graph.
2. **Services** (`services.py`) provide a single façade for persistence, business lookups, and external integrations (Twilio, weather heuristics, etc.).
3. **Toolkit** (`toolkit/`) contains pluggable tools that operate on the conversation state. Tools describe when they apply, what they update, and any follow-up actions.
4. **Nodes & graph** (`nodes.py`, `graph.py`) orchestrate the LangGraph flow: ingest messages, execute the registered tools, and craft the final response.
5. **Planner & OpenAI** (`planner.py`, `openai_client.py`) encapsulate domain-specific logic used by tools and response generation.

## 🧱 Core modules

### `types.py`

Base Pydantic models exchanged between the REST API and the agent: `ChatRequest`, `ChatResponse`, `ChatToolResult`, and enumerated chat roles.

### `conversation_models.py`

Dataclasses used internally by the graph:

- `FishingPlanDetails`, `WeatherReport`, `FishReport`, `CallSummary` capture state collected from tools.
- `PlanSnapshot` bundles the persisted plan record plus derived details.
- `ConversationState` (a `TypedDict`) documents the shape of the data passed between LangGraph nodes; it now includes handles for `AgentServices`, the `ToolRegistry`, and the latest `PlanSnapshot`.

### `services.py`

`AgentServices` centralizes domain operations:

- Loading and persisting plans via `crud`/`models`.
- Listing and selecting fishing businesses, and starting reservation calls (Twilio integration).
- Utility helpers such as `resolve_target_date` used by multiple tools.

`conversation_tools.py` simply re-exports `AgentServices` as `ConversationTools` for backward compatibility.

### `tool_results.py`

`make_tool_result` is a helper for constructing `ChatToolResult` entries with consistent IDs and timestamps.

### `planner.py`

Contains the NLP-ish heuristic planner that extracts structured fishing plan details from free-form user messages. Exposes a `PlannerAgent` and module-level singleton `planner_agent` used by the planner tool.

### `openai_client.py`

Thin wrapper around OpenAI's Chat Completions API with lazy initialization and fallbacks for environments where OpenAI is disabled.

## 🧰 Toolkit internals

### `toolkit/base.py`

Defines the building blocks for tools:

- `ToolContext` provides access to `AgentServices` and the current conversation state.
- `ToolOutput` accumulates state updates, tool results, and optional follow-up actions.
- `ConversationTool` protocol and `BaseTool` helper simplify authoring new tools.

### `toolkit/registry.py`

`ToolRegistry` stores tool instances, exposes name-based lookups, and can order tools according to a requested action sequence.

### `toolkit/builtins/`

Default tool implementations bundled with the agent:

- `WeatherTool` produces `WeatherReport` updates.
- `FishInsightsTool` adds recent catch heuristics.
- `PlannerTool` runs `planner_agent`, persists results, and records missing fields.
- `CallTool` initiates Twilio calls and persists outcomes.

The package-level factory (`toolkit/builtins/__init__.py`) exposes `default_tools()` and `create_default_registry()` to assemble these tools for the agent.

## 🧠 Nodes and graph

### `nodes.py`

Key nodes in the LangGraph state machine:

- `chat_agent_node` loads the latest plan snapshot via `AgentServices`, determines missing information/actions, and seeds the tool registry.
- `tool_runner_node` iterates through the registry, executing any tools whose `applies_to` method returns `True`. It merges updates, accumulates tool results, and adds follow-up actions dynamically.
- `compose_response_node` produces the final `ChatResponse`, optionally leveraging OpenAI for natural-language output.

### `graph.py`

`build_fishing_planner_graph()` wires the nodes into a simple pipeline: chat → tool runner → compose. `FishingPlannerAgent` owns a compiled graph, injects `AgentServices` and the default registry factory, and exposes a callable interface used by API routes or tests. Consumers can supply a custom `registry_factory` or `extra_state` dict for experimentation.

## 🚀 Extending the agent

1. **Add a new tool** by subclassing `BaseTool` (or implementing `ConversationTool`) and registering it in a custom `ToolRegistry`.
2. **Inject the registry** when constructing `FishingPlannerAgent`:

   ```python
   from server.src.agent import FishingPlannerAgent, ToolRegistry
   from server.src.agent.toolkit.builtins import create_default_registry

   def registry_factory() -> ToolRegistry:
       registry = create_default_registry()
       registry.register(MyCustomTool())
       return registry

   agent = FishingPlannerAgent(registry_factory=registry_factory)
   ```

3. **Expose new state** via `ToolOutput.updates`; nodes automatically propagate plan snapshots, tool results, and follow-up actions.

## ✅ Testing

The server test suite (`server/src/tests/test_api.py`) exercises the `/chat` endpoint end-to-end. Run the entire backend suite from the `server` directory:

```bash
cd server
pytest
```

## 📚 Additional docs

- `agent_requirements.md` captures the original blueprint and acceptance criteria for the LangGraph agent.
- The FastAPI entrypoint (`server/src/app/main.py`) shows how the agent is instantiated and invoked within the HTTP layer.

With this structure, you can grow the assistant by dropping in new tools, tweaking planner heuristics, or swapping the response generator without disturbing the overall conversation flow.
