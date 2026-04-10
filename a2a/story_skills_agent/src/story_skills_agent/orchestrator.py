from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner

from story_skills_agent.adk_agent import build_agent as build_story_agent
from story_skills_agent.configuration import Configuration
from story_skills_agent.diagnostics_agent import build_diagnostics_agent

APP_NAME = "kagenti_agent"

ORCHESTRATOR_INSTRUCTION = """\
You are the Kagenti platform assistant. Your job is to route user requests to the right specialist.

**Routing rules — transfer immediately without additional commentary:**

- If the user asks to **write a story**, create fiction, or anything related to creative writing \
→ transfer to `CollaborativeStoryWorkflow`

- If the user asks about **agent health**, pod issues, deployment problems, container logs, \
cluster diagnostics, or anything related to Kubernetes/OpenShift troubleshooting \
→ transfer to `AgentDiagnosticsWorkflow`

Do NOT attempt to answer the request yourself. Always transfer to the appropriate workflow.
"""


def _build_model(config: Configuration) -> LiteLlm:
    return LiteLlm(
        model=config.llm_model,
        api_base=config.llm_api_base,
        api_key=config.llm_api_key,
    )


def build_orchestrator(config: Configuration | None = None) -> LlmAgent:
    if config is None:
        config = Configuration()

    model = _build_model(config)

    story_agent = build_story_agent(config)
    diagnostics_agent = build_diagnostics_agent(model, config)

    return LlmAgent(
        name="KagentiOrchestrator",
        model=model,
        instruction=ORCHESTRATOR_INSTRUCTION,
        description="Routes requests to story writing or agent diagnostics workflows.",
        sub_agents=[story_agent, diagnostics_agent],
    )


def get_runner(config: Configuration | None = None) -> InMemoryRunner:
    agent = build_orchestrator(config)
    return InMemoryRunner(agent=agent, app_name=APP_NAME)
