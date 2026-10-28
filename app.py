import asyncio
import os

from dotenv import load_dotenv
from autogen_agentchat.messages import MemoryQueryEvent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_core.memory import ListMemory
from backend.agents import create_agents


load_dotenv()


async def main():
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is missing from .env")

    model_client = OpenAIChatCompletionClient(model="gpt-4o-mini")

    # ListMemory stores project facts saved by the Main Agent.
    # It is separate from agent history, so it survives 'new chat'.
    project_memory = ListMemory()

    

    agents = create_agents(model_client, project_memory)
    main_agent = agents[0]

    try:
        while True:
            try:
                user_request = input(
                    "\nRequest ('memory', 'new chat', 'new session', 'exit'): "
                ).strip()
                command = user_request.lower()

                if command == "exit":
                    break

                if not user_request:
                    continue

                if command == "new chat":
                    # Fresh agents have empty histories. ListMemory is kept.
                    agents = create_agents(model_client, project_memory)
                    main_agent = agents[0]
                    print("New chat started. Agent histories cleared. Stored memory kept.")
                    continue

                if command == "new session":
                    # Clear both agent histories and stored memory.
                    await project_memory.clear()
                    agents = create_agents(model_client, project_memory)
                    main_agent = agents[0]
                    print("New session started. Agent histories and stored memory cleared.")
                    continue

                if command == "memory":
                    # ListMemory.query() ignores the query text and returns all items.
                    stored = await project_memory.query("")
                    if not stored.results:
                        print("[Memory] Nothing stored.")
                    for number, item in enumerate(stored.results, 1):
                        print(f"[Memory] {number}. {item.content}")
                    continue

                print("\nProcessing...\n")
                print("[Main Agent] Working...")
                result = await main_agent.run(task=user_request)
                response = str(result.messages[-1].content)
                print("[Main Agent] Completed.")

                # Show whether ListMemory was added to the Main Agent's context.
                memory_used = False
                for message in result.messages:
                    if isinstance(message, MemoryQueryEvent):
                        memory_used = True
                        print(f"[Memory] {len(message.content)} stored item(s) added to Main Agent context.")
                if not memory_used:
                    print("[Memory] Memory was empty before this request.")

                print("\n===== RESPONSE =====\n")
                print(response)

            except EOFError:
                print("\nExiting...")
                break            

    finally:
        await model_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C while agents are working cancels the run.
        print("\nExiting...")