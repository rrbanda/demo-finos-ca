import pathlib

from google.adk.agents import LlmAgent, LoopAgent, ParallelAgent, SequentialAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import InMemoryRunner
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from story_skills_agent.configuration import Configuration
from story_skills_agent import instructions

N_CHAPTERS = 3
MAX_WORDS = 100

KEY_USER_PROMPT = "user_prompt"
KEY_ENHANCED_PROMPT = "enhanced_prompt"
KEY_CURRENT_STORY = "current_story"
KEY_CREATIVE_CANDIDATE = "creative_chapter_candidate"
KEY_FOCUSED_CANDIDATE = "focused_chapter_candidate"
KEY_FINAL_STORY = "final_story"

APP_NAME = "story_skills_agent"


def _build_model(config: Configuration) -> LiteLlm:
    return LiteLlm(
        model=config.llm_model,
        api_base=config.llm_api_base,
        api_key=config.llm_api_key,
    )


def _build_skill_toolset() -> SkillToolset:
    skills_root = pathlib.Path(__file__).parent / "skills"
    skill_names = [
        "genre-guide",
        "story-structure",
        "character-builder",
    ]
    skill_list = []
    for name in skill_names:
        skill_dir = skills_root / name
        if skill_dir.exists():
            skill_list.append(load_skill_from_dir(skill_dir))
    return SkillToolset(skills=skill_list)


def set_initial_story(callback_context, llm_request):
    callback_context.state[KEY_CURRENT_STORY] = "Chapter 1"


def build_agent(config: Configuration | None = None) -> SequentialAgent:
    if config is None:
        config = Configuration()

    model = _build_model(config)
    skill_toolset = _build_skill_toolset()

    prompt_enhancer = LlmAgent(
        name="PromptEnhancerAgent",
        model=model,
        instruction=instructions.PROMPT_ENHANCER_INSTRUCTION,
        description="Expands user prompt into a full story premise using writing skills.",
        output_key=KEY_ENHANCED_PROMPT,
        before_model_callback=set_initial_story,
        tools=[skill_toolset],
    )

    creative_writer = LlmAgent(
        name="CreativeStoryTellerAgent",
        model=model,
        generate_content_config=types.GenerateContentConfig(temperature=0.9),
        instruction=instructions.CREATIVE_WRITER_INSTRUCTION.format(max_words=MAX_WORDS),
        description="Writes a creative, high-temperature chapter draft.",
        output_key=KEY_CREATIVE_CANDIDATE,
    )

    focused_writer = LlmAgent(
        name="FocusedStoryTellerAgent",
        model=model,
        generate_content_config=types.GenerateContentConfig(temperature=0.2),
        instruction=instructions.FOCUSED_WRITER_INSTRUCTION.format(max_words=MAX_WORDS),
        description="Writes a consistent, low-temperature chapter draft.",
        output_key=KEY_FOCUSED_CANDIDATE,
    )

    critique_agent = LlmAgent(
        name="CritiqueAgent",
        model=model,
        instruction=instructions.CRITIQUE_AGENT_INSTRUCTION,
        description="Selects the best chapter and updates the story state.",
        output_key=KEY_CURRENT_STORY,
    )

    editor_agent = LlmAgent(
        name="EditorAgent",
        model=model,
        instruction=instructions.EDITOR_AGENT_INSTRUCTION,
        description="Polishes the final draft.",
        output_key=KEY_FINAL_STORY,
    )

    parallel_writers = ParallelAgent(
        name="ParallelChapterGenerators",
        sub_agents=[creative_writer, focused_writer],
        description="Generates two chapter options in parallel.",
    )

    chapter_cycle = SequentialAgent(
        name="ChapterGenerationCycle",
        sub_agents=[parallel_writers, critique_agent],
        description="Runs parallel writers then selects the best chapter.",
    )

    story_loop = LoopAgent(
        name="StoryBuildingLoop",
        sub_agents=[chapter_cycle],
        max_iterations=N_CHAPTERS,
        description=f"Iteratively writes {N_CHAPTERS} chapters.",
    )

    root_agent = SequentialAgent(
        name="CollaborativeStoryWorkflow",
        sub_agents=[prompt_enhancer, story_loop, editor_agent],
        description="End-to-end story generation pipeline with writing skills.",
    )

    return root_agent


def get_runner(config: Configuration | None = None) -> InMemoryRunner:
    agent = build_agent(config)
    return InMemoryRunner(agent=agent, app_name=APP_NAME)
