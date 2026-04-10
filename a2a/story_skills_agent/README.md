# Kagenti Agent (Google ADK)

A multi-skill agent built with **Google ADK**, exposed as a **Kagenti A2A agent**. An orchestrator routes requests to either a **collaborative story writing pipeline** or an **agent diagnostics workflow** that inspects Kubernetes/OpenShift clusters via MCP.

## What It Demonstrates

- **Multi-Agent Orchestration**: `KagentiOrchestrator` routes to two workflows composed of 8+ LLM agents using `SequentialAgent`, `ParallelAgent`, and `LoopAgent`
- **ADK Skills**: 4 file-based skills (genre-guide, story-structure, character-builder, troubleshooting-guide) loaded via `SkillToolset`
- **MCPToolset**: Connects to a Kubernetes MCP server for live cluster inspection (pods, logs, events)
- **LlamaStack Integration**: Uses `LiteLlm` to connect ADK to any OpenAI-compatible endpoint
- **A2A Protocol**: Wraps the ADK agent in an A2A server for Kagenti discovery and orchestration

## Architecture

```
User → A2A Server → KagentiExecutor → KagentiOrchestrator (LlmAgent)
                                          ├─ CollaborativeStoryWorkflow (SequentialAgent)
                                          │   ├─ PromptEnhancer (+ SkillToolset)
                                          │   ├─ LoopAgent × 3
                                          │   │   ├─ ParallelAgent
                                          │   │   │   ├─ CreativeWriter (temp=0.9)
                                          │   │   │   └─ FocusedWriter (temp=0.2)
                                          │   │   └─ CritiqueAgent
                                          │   └─ EditorAgent
                                          └─ AgentDiagnosticsWorkflow (SequentialAgent)
                                              ├─ ClusterInspectorAgent (+ MCPToolset + SkillToolset)
                                              ├─ LogAnalyzerAgent (+ MCPToolset + SkillToolset)
                                              └─ DiagnosticsReporterAgent
```

## Quick Start (Local)

```bash
cp .env.example .env
uv sync
uv run server
```

### Verify the server is running

```bash
# Health check
curl -s http://localhost:8000/health
# → {"status":"ok"}

# Fetch the agent card
curl -s http://localhost:8000/.well-known/agent-card.json | python3 -m json.tool
```

### Test story writing (A2A client)

```python
import asyncio
import httpx
from a2a.client import ClientFactory, ClientConfig, create_text_message_object

async def test_story():
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    config = ClientConfig(httpx_client=http_client)
    client = await ClientFactory.connect(agent='http://localhost:8000', client_config=config)
    message = create_text_message_object(
        content='Write a very short story about a robot learning to paint'
    )
    async for event in client.send_message(message):
        if isinstance(event, tuple):
            task, update = event
            print(f"Task {task.id}: {task.status.state}")
            if task.artifacts:
                for artifact in task.artifacts:
                    for part in artifact.parts:
                        if hasattr(part, 'text'):
                            print(part.text[:300] + "...")

asyncio.run(test_story())
```

### Test agent diagnostics (A2A client)

```python
import asyncio
import httpx
from a2a.client import ClientFactory, ClientConfig, create_text_message_object

async def test_diagnostics():
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
    config = ClientConfig(httpx_client=http_client)
    client = await ClientFactory.connect(agent='http://localhost:8000', client_config=config)
    message = create_text_message_object(
        content='Check the health of all agents in namespace team1'
    )
    async for event in client.send_message(message):
        if isinstance(event, tuple):
            task, update = event
            print(f"Task {task.id}: {task.status.state}")
            if task.artifacts:
                for artifact in task.artifacts:
                    for part in artifact.parts:
                        if hasattr(part, 'text'):
                            print(part.text[:500] + "...")

asyncio.run(test_diagnostics())
```

### Validate agent card programmatically

```bash
curl -s http://localhost:8000/.well-known/agent-card.json | python3 -c "
import json, sys
card = json.load(sys.stdin)
assert card['name'] == 'Kagenti Agent (Google ADK)'
assert card['version'] == '0.2.0'
skill_ids = [s['id'] for s in card['skills']]
assert 'story_writer' in skill_ids
assert 'agent_diagnostics' in skill_ids
print(f'OK: {card[\"name\"]} v{card[\"version\"]} — skills: {skill_ids}')
"
# → OK: Kagenti Agent (Google ADK) v0.2.0 — skills: ['story_writer', 'agent_diagnostics']
```

## Deploy on OpenShift / Kagenti

```bash
# Build image
oc new-build --binary --name=story-skills-agent
oc start-build story-skills-agent --from-dir=. --follow

# Deploy
oc apply -f deployment/k8s.yaml
oc expose svc/story-skills-agent
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `LLM_API_BASE` | LlamaStack URL | OpenAI-compatible API base URL |
| `LLM_API_KEY` | `not-needed` | API key for the LLM endpoint |
| `LLM_MODEL` | `openai/gemini/models/gemini-2.5-flash` | LiteLLM model string |
| `AGENT_ENDPOINT` | `http://localhost:8000/` | Public URL for the Agent Card |
| `OCP_MCP_URL` | K8s MCP SSE endpoint | Kubernetes MCP server URL for diagnostics |
