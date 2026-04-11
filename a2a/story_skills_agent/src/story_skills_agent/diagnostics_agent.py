import pathlib

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams

from story_skills_agent.configuration import Configuration
from story_skills_agent import diagnostics_instructions as instructions

KEY_CLUSTER_FINDINGS = "cluster_findings"
KEY_LOG_FINDINGS = "log_findings"
KEY_DIAGNOSTICS_REPORT = "diagnostics_report"


def _build_k8s_toolset(config: Configuration) -> MCPToolset:
    return MCPToolset(
        connection_params=SseConnectionParams(url=config.ocp_mcp_url),
        tool_filter=[
            "pods_list_in_namespace",
            "pods_get",
            "pods_log",
            "pods_top",
            "events_list",
            "resources_get",
            "resources_list",
        ],
    )


def _load_diagnostics_skill_content() -> str:
    """Read troubleshooting skill at build time and return its text."""
    path = pathlib.Path(__file__).parent / "skills" / "troubleshooting-guide" / "SKILL.md"
    return path.read_text() if path.exists() else ""


def build_diagnostics_agent(
    model: LiteLlm, config: Configuration
) -> SequentialAgent:
    k8s_toolset = _build_k8s_toolset(config)
    skill_content = _load_diagnostics_skill_content()

    cluster_inspector = LlmAgent(
        name="ClusterInspectorAgent",
        model=model,
        instruction=instructions.CLUSTER_INSPECTOR_INSTRUCTION.format(
            skill_content=skill_content
        ),
        description="Inspects Kubernetes cluster state for agent pods, deployments, services, and events.",
        tools=[k8s_toolset],
        output_key=KEY_CLUSTER_FINDINGS,
    )

    log_analyzer = LlmAgent(
        name="LogAnalyzerAgent",
        model=model,
        instruction=instructions.LOG_ANALYZER_INSTRUCTION,
        description="Reads container logs of problematic pods and identifies error patterns.",
        tools=[k8s_toolset],
        output_key=KEY_LOG_FINDINGS,
    )

    diagnostics_reporter = LlmAgent(
        name="DiagnosticsReporterAgent",
        model=model,
        instruction=instructions.DIAGNOSTICS_REPORTER_INSTRUCTION,
        description="Synthesizes cluster and log findings into a structured diagnostic report.",
        output_key=KEY_DIAGNOSTICS_REPORT,
    )

    return SequentialAgent(
        name="AgentDiagnosticsWorkflow",
        sub_agents=[cluster_inspector, log_analyzer, diagnostics_reporter],
        description=(
            "Diagnoses issues with Kagenti agents deployed on OpenShift/Kubernetes. "
            "Inspects pod status, analyzes logs, and produces actionable diagnostic reports."
        ),
    )
