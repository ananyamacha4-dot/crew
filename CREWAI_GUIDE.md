# CrewAI — Developer Guide

> Reference doc for the CTO task: build multi-role agents with **prompt orchestration** (one prompt → router picks the right role → answer).

---

## 0. Security — fix this first

The reference notebook `crewai.ipynb` has **hardcoded API keys in plain text** (cell 1 and cell 6 — OpenAI + Serper).

**Action items:**
1. Revoke the leaked OpenAI key: https://platform.openai.com/api-keys
2. Revoke the leaked Serper key: https://serper.dev/api-key
3. Create new keys.
4. Store them in a `.env` file (never in code, never in notebooks pushed to git):

```bash
# .env
OPENAI_API_KEY=sk-...
SERPER_API_KEY=...
```

5. Load them in Python:

```python
from dotenv import load_dotenv
load_dotenv()  # reads .env into os.environ
```

6. Add `.env` to `.gitignore`.

---

## 1. What is CrewAI?

CrewAI is a Python framework for building **multi-agent LLM systems**.

- One LLM call → a chatbot.
- Many LLM calls, each with a **role**, talking to each other → a "crew".

### Mental model (mapped to web-dev concepts)

| Web dev | CrewAI |
|---|---|
| Microservice / worker | `Agent` (one LLM with a role) |
| HTTP request / job | `Task` (a unit of work) |
| Job queue / orchestrator | `Crew` (runs the tasks) |
| External API client | `Tool` (search, file I/O, code exec) |
| Pipeline mode | `Process.sequential` or `Process.hierarchical` |

**Formula:**
`CrewAI = Agents × Tasks × Tools × Process`

---

## 2. Why use it (vs. raw OpenAI API)

Raw OpenAI = one model, one prompt, one answer.

The CTO's task ("prompt understands and selects role") requires:

1. A **router** — decides which role should answer.
2. A **state machine** — sequence between roles.
3. A **delegation protocol** — agents asking each other for help.
4. **Tool calling** — search, file I/O, code execution.
5. **Context passing** between calls.
6. Retries, max iterations, error handling.

CrewAI gives all of these as **declarative primitives**. You declare what you want; the framework runs the orchestration loop.

### Use it when

- Multi-step tasks needing specialization (research → write, code → test).
- You want the LLM to **dynamically decide** who does what.
- You need tool use across multiple steps.

### Don't use it when

- Simple single-turn Q&A — call the LLM directly.
- Strict deterministic pipeline — a normal job queue is cheaper.
- Sub-second latency required — multi-agent = many LLM calls = slow + expensive.

---

## 3. The 4 building blocks

### 3.1 `Agent` — a role-playing LLM worker

```python
from crewai import Agent

researcher = Agent(
    role='Researcher',                            # WHO it is
    goal='Find accurate, up-to-date info',        # WHAT it should achieve
    backstory="You are a senior research analyst...",  # personality / context
    tools=[search_tool],                          # what it can DO
    llm="gpt-4o",                                 # which model powers it
    allow_delegation=True,                        # can ask other agents for help
    max_iter=3,                                   # cap thinking loops
    cache=True,
    verbose=True,
)
```

**Key fields:**

| Field | Purpose |
|---|---|
| `role` / `goal` / `backstory` | Stitched into the system prompt. **These ARE the prompt.** |
| `tools` | Functions the LLM can call (OpenAI function-calling under the hood) |
| `allow_delegation=True` | This agent can hand sub-tasks to other agents. **Key for orchestration.** |
| `max_iter` | Safety cap so the agent doesn't loop forever |
| `llm` | Model name or LangChain LLM instance |

### 3.2 `Task` — a unit of work

```python
from crewai import Task

task = Task(
    description='Find and summarize latest AI news from last 1 month.',
    expected_output='Bullet list of 5 items.',
    agent=researcher,             # who is assigned (optional in hierarchical)
    async_execution=True,         # run in parallel with other async tasks
    context=[other_task],         # depends on another task's output
    tools=[search_tool],          # task-specific tools (overrides agent's)
    output_file='report.md',      # optional: write result to disk
)
```

`context=[task_a, task_b]` is the dependency arrow — task uses outputs of A and B as input.

### 3.3 `Tool` — what an agent can DO

A `Tool` is a Python function the LLM can call.

**Built-in tools:**

```python
from crewai_tools import (
    SerperDevTool,        # google search
    FileReadTool,         # read a file
    DirectoryReadTool,    # list a folder
    WebsiteSearchTool,    # RAG over a website
)
```

**Custom tool from any function:**

```python
from crewai.tools import tool

@tool("Multiplier")
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
```

Without tools, an agent can only **think and talk**. With tools, it can **act**.

### 3.4 `Crew` — the orchestrator

```python
from crewai import Crew, Process

crew = Crew(
    agents=[researcher, writer],
    tasks=[task1, task2],
    process=Process.sequential,   # or Process.hierarchical
    verbose=True,
)
result = crew.kickoff()           # the "run" button
```

**The two `Process` modes — this is the most important decision:**

| Mode | How it works | Use for |
|---|---|---|
| `Process.sequential` (default) | Tasks run in order, output of N → input of N+1 | Fixed pipeline (research → write) |
| `Process.hierarchical` | A **manager LLM** routes tasks to agents dynamically | **Prompt orchestration ← CTO task** |

---

## 4. The CTO task → `Process.hierarchical`

The CTO said:

> *"make agent of different roles and it should prompt orchestration — orchestration of models by giving prompts and it understands by that selects roles and gives answer"*

This is exactly what `Process.hierarchical` does:

```
        ┌──────────────────────────┐
USER ──▶│  Manager LLM (router)    │   ◀── picks which agent based on prompt
        └──────────┬───────────────┘
                   │ delegates
        ┌──────────┼─────────────┬───────────┐
        ▼          ▼             ▼           ▼
   Researcher    Coder        Writer        QA
   (search)     (python)      (markdown)    (review)
```

### Minimal skeleton

```python
import os
from dotenv import load_dotenv
from crewai import Agent, Task, Crew, Process
from crewai_tools import SerperDevTool

load_dotenv()  # OPENAI_API_KEY, SERPER_API_KEY from .env

# 1) Specialist agents — each with ONE role
researcher = Agent(
    role="Researcher",
    goal="Find accurate, up-to-date information from the web",
    backstory="You are a senior research analyst skilled at finding "
              "credible sources and summarizing them.",
    tools=[SerperDevTool()],
    allow_delegation=False,
)

coder = Agent(
    role="Python Developer",
    goal="Write clean, working Python code for any request",
    backstory="You are a senior Python engineer who writes idiomatic, "
              "tested code with clear comments.",
    allow_delegation=False,
)

writer = Agent(
    role="Technical Writer",
    goal="Explain technical topics clearly in markdown",
    backstory="You write developer-facing documentation. You use short "
              "sentences, code examples, and tables.",
    allow_delegation=False,
)

qa = Agent(
    role="QA Reviewer",
    goal="Review outputs for accuracy, bugs, and clarity",
    backstory="You are a meticulous reviewer who catches bugs and "
              "unclear explanations before they reach users.",
    allow_delegation=False,
)

# 2) ONE task — the user's prompt. NO `agent=` → manager picks.
user_prompt = "Research the latest LangGraph release and write a 200-word summary."

task = Task(
    description=user_prompt,
    expected_output="Final answer to the user's request, in markdown.",
)

# 3) Crew in hierarchical mode — `manager_llm` is the router brain
crew = Crew(
    agents=[researcher, coder, writer, qa],
    tasks=[task],
    process=Process.hierarchical,
    manager_llm="gpt-4o",   # the routing LLM
    verbose=True,
)

result = crew.kickoff()
print(result)
```

### What happens at runtime

1. `kickoff()` sends the prompt to the **manager LLM**.
2. Manager reads each agent's `role` + `goal` + `backstory` — **this is the manager's menu of options.**
3. Manager decides: *"this is research → Researcher"*. Researcher returns notes.
4. Manager decides next: *"summarize → Writer with researcher's notes as context"*.
5. Final output is returned.

**The prompt itself drives the routing.** That is exactly what the CTO asked for.

### Tips for good routing

- **Make `role` distinct.** Avoid overlap. "Researcher" + "Web Search Specialist" confuses the manager — merge them.
- **Make `goal` action-oriented.** "Find sources" beats "be smart".
- **Use `backstory` to set constraints.** e.g., "always cite sources", "never write code longer than 50 lines".
- **Set `allow_delegation=False` on workers** to keep the routing tree shallow (only the manager delegates).
- **Use a strong manager model** (`gpt-4o` / Claude Opus). A weak manager routes badly.

---

## 5. Code patterns from the reference notebook

### Pattern A — Sequential pipeline (notebook cell 6)

Two agents, two tasks, fixed order:

```python
research_agent = Agent(role='Researcher', ...)
writer_agent   = Agent(role='Blog writer', ...)

crew = Crew(
    agents=[research_agent, writer_agent],
    tasks=[research_task, write_task],   # runs in this order
    # process=Process.sequential is the default
)
```

### Pattern B — Async parallel tasks with a dependent collector (notebook cell 11)

Two tasks run in parallel, a third waits for both:

```python
list_ideas = Task(..., agent=research_agent, async_execution=True)
list_history = Task(..., agent=research_agent, async_execution=True)

write_article = Task(
    ...,
    agent=writer_agent,
    context=[list_ideas, list_history],   # waits for both
)

crew = Crew(agents=[...], tasks=[list_ideas, list_history, write_article])
```

### Pattern C — Agent with code execution (notebook cell 8)

```python
from langchain_experimental.utilities import PythonREPL
python_repl = PythonREPL()

coder = Agent(
    role='Senior programmer',
    tools=[python_repl],   # agent can EXECUTE python
    ...
)
```

⚠️ Code execution is powerful but dangerous — only enable in sandboxed environments.

---

## 6. Common pitfalls

| Pitfall | Fix |
|---|---|
| Hardcoded API keys in notebook | `.env` + `python-dotenv` |
| Manager LLM picks the wrong agent | Sharpen `role`/`goal`/`backstory`; use a stronger `manager_llm` |
| Infinite loop / runaway cost | Set `max_iter` on agents and `max_rpm` |
| `allow_delegation=True` on every agent → chaos | Only the manager (or a clearly defined lead) delegates |
| Same `role` string on two agents | Manager can't distinguish — make roles unique |
| Importing `ChatOpenAI` from `langchain.chat_models` | Deprecated. Use `from langchain_openai import ChatOpenAI` |
| `crewai` version mismatch | Pin in `requirements.txt`: `crewai==0.x.x`, `crewai-tools==0.x.x` |

---

## 7. Suggested project structure

```
crew-ai/
├── .env                  # API keys (gitignored)
├── .gitignore
├── requirements.txt
├── main.py               # CLI entry: python main.py "your prompt"
├── agents/
│   ├── __init__.py
│   ├── researcher.py
│   ├── coder.py
│   ├── writer.py
│   └── qa.py
├── tools/
│   └── custom_tools.py
└── crewai.ipynb          # reference / sandbox
```

`main.py` skeleton:

```python
import sys
from dotenv import load_dotenv
from crewai import Crew, Task, Process
from agents.researcher import researcher
from agents.coder import coder
from agents.writer import writer
from agents.qa import qa

load_dotenv()

def run(prompt: str) -> str:
    task = Task(
        description=prompt,
        expected_output="Final answer in markdown.",
    )
    crew = Crew(
        agents=[researcher, coder, writer, qa],
        tasks=[task],
        process=Process.hierarchical,
        manager_llm="gpt-4o",
        verbose=True,
    )
    return crew.kickoff()

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Hello, what can you do?"
    print(run(prompt))
```

`requirements.txt`:

```
crewai>=0.30.0
crewai-tools>=0.4.0
langchain-openai
python-dotenv
```

Run:

```bash
pip install -r requirements.txt
python main.py "Research LangGraph and write a summary"
```

---

## 8. Next steps for the CTO demo

1. Set up `.env` and the project structure above.
2. Build 4 specialist agents (Researcher, Coder, Writer, QA).
3. Wire them with `Process.hierarchical` + a manager LLM.
4. Test with 3 different prompt types to prove the router works:
   - Research prompt → expect Researcher to be picked first.
   - Code prompt → expect Coder.
   - Mixed prompt ("research X, then write code for it") → expect Researcher → Coder → QA chain.
5. Optional: wrap it in a FastAPI `POST /ask` endpoint for a web demo.
6. Log each routing decision (`verbose=True`) — useful to show the CTO *how* the prompt drove the routing.

---

## 9. Reference links

- CrewAI docs: https://docs.crewai.com
- CrewAI GitHub: https://github.com/joaomdmoura/crewAI
- CrewAI Tools: https://github.com/joaomdmoura/crewAI-tools
- Serper (search API): https://serper.dev
- OpenAI keys dashboard: https://platform.openai.com/api-keys
