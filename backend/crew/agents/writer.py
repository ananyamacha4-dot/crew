import os
from crewai import Agent


def build_writer() -> Agent:
    return Agent(
        role="Technical Writer",
        goal=(
            "Turn raw notes, data, or research into clear written content in "
            "markdown. Match the length and tone the user asked for."
        ),
        backstory=(
            "You write developer-facing documentation and blog posts. You use "
            "short sentences, headings, bullet lists, and code blocks. You avoid "
            "jargon unless the audience expects it."
        ),
        llm=os.getenv("WORKER_MODEL", "groq/llama-3.1-8b-instant"),
        allow_delegation=False,
        max_iter=3,
        verbose=True,
    )
