from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuration(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    llm_model: str = "openai/gemini/models/gemini-2.5-flash"
    llm_api_base: str = "https://llamastack-llamastack.apps.ocp.v7hjl.sandbox2288.opentlc.com/v1"
    llm_api_key: str = "not-needed"
    agent_endpoint: str = "http://localhost:8000/"
    ocp_mcp_url: str = "https://kubernetes-mcp-server-ocp-mcp-server.apps.ocp.v7hjl.sandbox2288.opentlc.com/sse"
