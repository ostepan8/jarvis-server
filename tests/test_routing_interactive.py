#!/usr/bin/env python3
"""
Interactive routing test script.

Run with: python tests/test_routing_interactive.py

Or with real LLM: USE_REAL_LLM=1 python tests/test_routing_interactive.py
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from jarvis.core.system import JarvisSystem
from jarvis.core.config import JarvisConfig
from jarvis.logging import JarvisLogger
from tests.tools.routing_tracker import RoutingTracker, wrap_network_with_tracker


USE_REAL_LLM = os.getenv("USE_REAL_LLM", "0") == "1"


async def test_routing_flow(user_input: str, use_real_llm: bool = False):
    """
    Test the routing flow for a given user input.

    Args:
        user_input: The user's request string
        use_real_llm: If True, use real LLM (requires API keys)

    Returns:
        Tuple of (response, tracker)
    """
    print(f"\n{'='*70}")
    print(f"Testing routing for: '{user_input}'")
    print(f"{'='*70}\n")

    # Create tracker
    tracker = RoutingTracker()

    # Create config
    if use_real_llm:
        config = JarvisConfig(
            ai_provider="openai",
            api_key=os.getenv("OPENAI_API_KEY"),
            response_timeout=30.0,
            intent_timeout=10.0,
        )
    else:
        # Use dummy config for mock testing
        config = JarvisConfig(
            ai_provider="dummy",
            response_timeout=10.0,
            intent_timeout=5.0,
        )

    # Create system
    jarvis = JarvisSystem(config)

    # Wrap network with tracker
    wrap_network_with_tracker(jarvis.network, tracker)

    await jarvis.initialize()

    try:
        # Process request
        result = await jarvis.process_request(
            user_input=user_input,
            tz_name="UTC",
            metadata=None,
        )

        # Get all flows (there should be one main request_id)
        all_flows = tracker.get_all_flows()

        print("\n" + "=" * 70)
        print("ROUTING FLOW ANALYSIS")
        print("=" * 70)

        # Print all flows
        for request_id, flow in all_flows.items():
            print(f"\nRequest ID: {request_id}")
            print(tracker.format_flow_diagram(request_id))

            # Show participants
            participants = tracker.get_agent_participants(request_id)
            print(f"\nAgents involved: {', '.join(participants)}")

        # Show capability usage
        print("\n" + "-" * 70)
        print("CAPABILITY USAGE:")
        print("-" * 70)
        for capability in [
            "control_lights",
            "get_today_schedule",
            "get_weather",
            "chat",
        ]:
            events = tracker.get_capability_usage(capability)
            if events:
                print(f"  {capability}: {len(events)} request(s)")
                for event in events:
                    print(f"    - {event.from_agent} → {event.to_agent or 'ALL'}")

        print("\n" + "=" * 70)
        print(f"RESULT: {result.get('response', 'No response')}")
        print("=" * 70 + "\n")

        return result, tracker

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback

        traceback.print_exc()
        return None, tracker
    finally:
        await jarvis.shutdown()


async def interactive_test():
    """Interactive test mode."""
    print("\n" + "=" * 70)
    print("INTERACTIVE ROUTING TEST")
    print("=" * 70)
    print("\nEnter user requests to test routing flows.")
    print("Commands:")
    print("  'exit' or 'quit' - Exit")
    print("  'flow' - Show flow analysis")
    print("  'clear' - Clear tracker")
    print("=" * 70 + "\n")

    tracker = None

    while True:
        try:
            user_input = input("\nEnter request (or 'exit' to quit): ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit"]:
                break

            if user_input.lower() == "flow" and tracker:
                print("\nLast flow:")
                all_flows = tracker.get_all_flows()
                for req_id, flow in all_flows.items():
                    print(tracker.format_flow_diagram(req_id))
                continue

            if user_input.lower() == "clear":
                if tracker:
                    tracker.reset()
                print("Tracker cleared.")
                continue

            # Run test
            result, tracker = await test_routing_flow(
                user_input, use_real_llm=USE_REAL_LLM
            )

        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except EOFError:
            break


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Test agent routing flows")
    parser.add_argument("--input", "-i", help="Single input to test")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    parser.add_argument("--real-llm", action="store_true", help="Use real LLM")

    args = parser.parse_args()

    use_real_llm = args.real_llm or USE_REAL_LLM

    if args.input:
        # Single test
        result, tracker = await test_routing_flow(args.input, use_real_llm)
    else:
        # Interactive mode
        await interactive_test()


if __name__ == "__main__":
    asyncio.run(main())
