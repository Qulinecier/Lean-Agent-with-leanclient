"""Entry point for the split Lean OpenAI agent."""
from __future__ import annotations

try:
    from .reading_agent import reading_agent
    from .running_agent import run_agent
except ImportError:  # Allows running `python main.py` from this folder.
    from reading_agent import reading_agent
    from running_agent import run_agent


if __name__ == "__main__":
    # Run this once first if you want to build/update the learning file:
    # reading_agent()
    reading_agent()
    run_agent()
