import logging
import os
from textwrap import dedent

import uvicorn
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, TaskState, TextPart
from a2a.utils import new_agent_text_message, new_task
from google.genai import types

from story_skills_agent.adk_agent import KEY_FINAL_STORY
from story_skills_agent.configuration import Configuration
from story_skills_agent.diagnostics_agent import KEY_DIAGNOSTICS_REPORT
from story_skills_agent.orchestrator import APP_NAME, get_runner

_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, _log_level, logging.INFO))
logger = logging.getLogger(__name__)
logging.getLogger("google.adk").setLevel(logging.DEBUG)
logging.getLogger("google.adk.tools").setLevel(logging.DEBUG)
logging.getLogger("google.adk.skills").setLevel(logging.DEBUG)

_runner = None
_sessions: dict[str, str] = {}


def _get_runner():
    global _runner
    if _runner is None:
        os.environ.setdefault("OPENAI_API_KEY", "not-needed")
        _runner = get_runner()
    return _runner


def get_agent_card(host: str, port: int) -> AgentCard:
    capabilities = AgentCapabilities(streaming=True)
    story_skill = AgentSkill(
        id="story_writer",
        name="Collaborative Story Writer",
        description=(
            "**Collaborative Story Writer** -- A multi-agent pipeline that writes "
            "creative stories using ADK Skills for genre, structure, and character guidance."
        ),
        tags=["story", "writing", "creative", "multi-agent", "adk", "skills"],
        examples=[
            "Write a short fantasy story about a dragon who learns to cook",
            "Create a mystery story set in a space station",
            "Write a thriller about a programmer who discovers a hidden message in code",
        ],
    )
    diagnostics_skill = AgentSkill(
        id="agent_diagnostics",
        name="Agent Diagnostics",
        description=(
            "**Agent Diagnostics** -- Diagnoses issues with Kagenti agents deployed on "
            "OpenShift/Kubernetes using the Kubernetes MCP server. Inspects pods, "
            "analyzes logs, and produces actionable diagnostic reports."
        ),
        tags=["diagnostics", "kubernetes", "openshift", "agent-health", "mcp", "sre"],
        examples=[
            "Why is my agent not responding in namespace team1?",
            "Check the health of all Kagenti agents on the cluster",
            "What's wrong with the story-skills-agent pod?",
        ],
    )
    return AgentCard(
        name="Kagenti Agent (Google ADK)",
        description=dedent("""\
            A multi-skill Kagenti agent built with Google ADK, demonstrating
            ADK Skills, MCPToolset, and multi-agent orchestration on Kagenti.

            ## Skills
            - **Story Writer**: Multi-agent creative writing pipeline with ADK Skills
            - **Agent Diagnostics**: Kubernetes/OpenShift agent health inspector via MCP

            ## Architecture
            - **KagentiOrchestrator** routes requests to the appropriate workflow
            - **CollaborativeStoryWorkflow** (SequentialAgent + ParallelAgent + LoopAgent)
            - **AgentDiagnosticsWorkflow** (SequentialAgent + MCPToolset + SkillToolset)

            ## Powered by
            - Google Agent Development Kit (ADK)
            - LlamaStack (gemini-2.5-flash via OpenAI-compatible API)
            - Kubernetes MCP Server for cluster inspection
            - ADK SkillToolset with 4 skills (3 writing + 1 troubleshooting)
        """),
        url=os.getenv("AGENT_ENDPOINT", f"http://{host}:{port}").rstrip("/") + "/",
        version="0.2.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=capabilities,
        skills=[story_skill, diagnostics_skill],
    )


class KagentiExecutor(AgentExecutor):
    """Bridges A2A protocol to the ADK orchestrator agent."""

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        task_updater = TaskUpdater(event_queue, task.id, task.context_id)

        user_input = context.get_user_input()
        logger.info("Kagenti agent received: %s (context=%s)", user_input, task.context_id)

        await task_updater.update_status(
            TaskState.working,
            new_agent_text_message(
                "Routing your request to the appropriate workflow...",
                task_updater.context_id,
                task_updater.task_id,
            ),
        )

        try:
            runner = _get_runner()
            context_id = task.context_id

            if context_id not in _sessions:
                session = await runner.session_service.create_session(
                    app_name=APP_NAME, user_id=context_id
                )
                _sessions[context_id] = session.id
            session_id = _sessions[context_id]

            content = types.Content(role="user", parts=[types.Part(text=user_input)])

            final_text = None
            async for event in runner.run_async(
                user_id=context_id, session_id=session_id, new_message=content
            ):
                if hasattr(event, "author") and event.author:
                    logger.info("ADK event from agent: %s", event.author)
                if hasattr(event, "content") and event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            logger.info(
                                "TOOL CALL: %s(%s)",
                                part.function_call.name,
                                part.function_call.args,
                            )
                        if hasattr(part, "function_response") and part.function_response:
                            logger.info(
                                "TOOL RESPONSE: %s -> %s",
                                part.function_response.name,
                                str(part.function_response.response)[:200],
                            )
                        if hasattr(part, "text") and part.text:
                            final_text = part.text

            if not final_text:
                session = await runner.session_service.get_session(
                    app_name=APP_NAME, user_id=context_id, session_id=session_id
                )
                final_text = (
                    session.state.get(KEY_FINAL_STORY)
                    or session.state.get(KEY_DIAGNOSTICS_REPORT)
                    or ""
                )

            if not final_text:
                final_text = "The pipeline completed but produced no output. Please try again with a different prompt."

            parts = [TextPart(text=final_text)]
            await task_updater.add_artifact(parts)
            await task_updater.complete()

        except Exception as e:
            logger.exception("Kagenti agent error: %s", e)
            parts = [TextPart(text=f"Error running pipeline: {e}")]
            await task_updater.add_artifact(parts)
            await task_updater.failed()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception("cancel not supported")


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


async def agent_card_compat(request: Request) -> JSONResponse:
    card = get_agent_card(host="0.0.0.0", port=8000)
    return JSONResponse(card.model_dump(mode="json", exclude_none=True))


def run():
    agent_card = get_agent_card(host="0.0.0.0", port=8000)

    request_handler = DefaultRequestHandler(
        agent_executor=KagentiExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build()

    app.routes.insert(0, Route("/health", health, methods=["GET"]))
    app.routes.insert(
        0, Route("/.well-known/agent-card.json", agent_card_compat, methods=["GET"])
    )

    uvicorn.run(app, host="0.0.0.0", port=8000)
