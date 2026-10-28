from autogen_agentchat.agents import AssistantAgent
from autogen_core.memory import MemoryContent, MemoryMimeType

# Create the specialist agents and Main Agent.
def create_agents(model_client, project_memory):
    requirements_analyst = AssistantAgent(
        name="requirements_analyst",
        model_client=model_client,
        system_message=(
            "You are a software requirements analyst. "
            "Identify functional requirements, assumptions, and acceptance criteria. "
            "Do not write implementation code."
        ),
    )

    security_reviewer = AssistantAgent(
        name="security_reviewer",
        model_client=model_client,
        system_message=(
            "You are a software security reviewer. "
            "Identify relevant security risks and recommend safeguards."
        ),
    )

    test_planner = AssistantAgent(
        name="test_planner",
        model_client=model_client,
        system_message=(
            "You are a software test planner. "
            "Create practical test cases covering normal usage, edge cases, "
            "and failure scenarios."
        ),
    )

    technical_lead = AssistantAgent(
        name="technical_lead",
        model_client=model_client,
        system_message=(
            "You are a software technical lead. "
            "Recommend a suitable architecture and implementation approach. "
            "Consider maintainability and the existing technology stack."
        ),
    )

    def add_numbers(a: float, b: float) -> str:
        """Add two numbers."""
        return f"{a} + {b} = {a + b}"

    calculator_agent = AssistantAgent(
        name="calculator_agent",
        model_client=model_client,
        tools=[add_numbers],
        max_tool_iterations=2,
        system_message=(
            "You are a calculator agent. "
            "Always use the add_numbers tool to add two numbers. "
            "Return the result clearly."
        ),
    )

    # These functions allow the Main Agent to call specialists.
    async def analyze_requirements(task: str) -> str:
        print("[Requirements Analyst] Working...")
        print(f"[Requirements Analyst] Task: {task}")
        result = await requirements_analyst.run(task=task)
        print("[Requirements Analyst] Completed.")
        return str(result.messages[-1].content)

    async def review_security(task: str) -> str:
        print("[Security Reviewer] Working...")
        print(f"[Security Reviewer] Task: {task}")
        result = await security_reviewer.run(task=task)
        print("[Security Reviewer] Completed.")
        return str(result.messages[-1].content)

    async def plan_tests(task: str) -> str:
        print("[Test Planner] Working...")
        print(f"[Test Planner] Task: {task}")
        result = await test_planner.run(task=task)
        print("[Test Planner] Completed.")
        return str(result.messages[-1].content)

    async def plan_implementation(task: str) -> str:
        print("[Technical Lead] Working...")
        print(f"[Technical Lead] Task: {task}")
        result = await technical_lead.run(task=task)
        print("[Technical Lead] Completed.")
        return str(result.messages[-1].content)

    async def calculate(task: str) -> str:
        print("[Calculator Agent] Working...")
        print(f"[Calculator Agent] Task: {task}")
        result = await calculator_agent.run(task=task)
        print("[Calculator Agent] Completed.")
        return str(result.messages[-1].content)

    # This tool lets the Main Agent decide what to store in ListMemory.
    async def save_project_fact(fact: str) -> str:
        """Save a lasting fact about the user's project."""
        await project_memory.add(
            MemoryContent(content=fact, mime_type=MemoryMimeType.TEXT)
        )
        print(f"[Memory] Saved: {fact}")
        return f"Saved: {fact}"

    main_agent = AssistantAgent(
        name="main_agent",
        model_client=model_client,
        tools=[
            analyze_requirements,
            review_security,
            plan_tests,
            plan_implementation,
            calculate,
            save_project_fact,
        ],
        memory=[project_memory],
        max_tool_iterations=8,
        system_message=(
            "You are the Main Agent coordinating a software development assistant.\n\n"
            "Available tools:\n"
            "- analyze_requirements: Requirements Analyst\n"
            "- review_security: Security Reviewer\n"
            "- plan_tests: Test Planner\n"
            "- plan_implementation: Technical Lead\n"
            "- calculate: Calculator Agent\n"
            "- save_project_fact: Save a lasting project fact to memory\n\n"
            "Instructions:\n"
            "- Understand the request before selecting tools.\n"
            "- Call only relevant specialists, not everyone automatically.\n"
            "- For software features, select specialists based on the task.\n"
            "- For simple addition, use only the Calculator Agent.\n"
            "- Do not use the Calculator Agent for unrelated tasks.\n"
            "- Use specialist results to prepare your response.\n"
            "- Do not claim a specialist was used unless its tool ran.\n"
            "- Keep responses concise and relevant.\n"
            "- Use previous conversation context to answer follow-up questions.\n"
            "- Stored project facts may be provided as memory. Use them when relevant.\n"
            "- When the user states a lasting fact about their project (tech stack, "
            "constraints, decisions, preferences), save it with save_project_fact. "
            "Do not save questions, temporary details, or facts already in memory."
        ),
    )

    return [
        main_agent,
        requirements_analyst,
        security_reviewer,
        test_planner,
        technical_lead,
        calculator_agent,
    ]