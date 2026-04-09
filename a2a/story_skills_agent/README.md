# Story Skills Agent (Google ADK on Kagenti)

A multi-agent story writing pipeline built with **Google ADK**, exposed as a **Kagenti A2A agent**. This is the first example of a Google ADK agent running on the Kagenti platform.

## What It Demonstrates

- **Multi-Agent Orchestration**: 5 LLM agents composed with `SequentialAgent`, `ParallelAgent`, and `LoopAgent`
- **ADK Skills**: 3 file-based skills (genre-guide, story-structure, character-builder) loaded via `SkillToolset`
- **LlamaStack Integration**: Uses `LiteLlm` to connect ADK to any OpenAI-compatible endpoint
- **A2A Protocol**: Wraps the ADK agent in an A2A server for Kagenti discovery and orchestration

## Architecture

```
User → A2A Server → StoryExecutor → ADK SequentialAgent
                                        ├─ PromptEnhancer (+ SkillToolset)
                                        ├─ LoopAgent × 3
                                        │   ├─ ParallelAgent
                                        │   │   ├─ CreativeWriter (temp=0.9)
                                        │   │   └─ FocusedWriter (temp=0.2)
                                        │   └─ CritiqueAgent
                                        └─ EditorAgent
```

## Quick Start (Local)

```bash
cp .env.example .env
uv sync
uv run server --host 0.0.0.0 --port 8000
```

Test:
```bash
curl http://localhost:8000/.well-known/agent-card.json
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
