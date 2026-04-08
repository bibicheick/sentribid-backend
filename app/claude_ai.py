# backend/app/claude_ai.py
"""
Claude AI Engine for SentriBiD v0.7.0
The most powerful AI model — used for:
- RFP shredding & compliance matrix
- War Room competitive analysis
- Proposal review & scoring
- Opportunity matching
- Ghost proposals & counter-strategies
- Proposal generation (now Claude-first)
"""

import os
import json
import logging
from typing import Optional

logger = logging.getLogger("sentribid.claude")


def _get_api_key() -> str:
    """Get Claude/Anthropic API key — checks BOTH env vars."""
    return (
        os.getenv("CLAUDE_API_KEY", "").strip()
        or os.getenv("ANTHROPIC_API_KEY", "").strip()
    )


def get_claude_client():
    """Initialize Anthropic client."""
    try:
        from anthropic import Anthropic
        api_key = _get_api_key()
        if not api_key:
            logger.warning("Neither CLAUDE_API_KEY nor ANTHROPIC_API_KEY set in .env")
            return None
        return Anthropic(api_key=api_key)
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return None
    except Exception as e:
        logger.error(f"Claude client init failed: {e}")
        return None


def call_claude(
    prompt: str,
    system_instruction: str = "You are a helpful assistant.",
    json_mode: bool = False,
    max_tokens: int = 8000,
    temperature: float = 0.3,
    model: str = None,
) -> Optional[str]:
    """
    Call Claude API.

    Args:
        prompt: The user message
        system_instruction: System prompt
        json_mode: If True, instructs Claude to return valid JSON
        max_tokens: Max response tokens
        temperature: 0.0-1.0 (lower = more focused)
        model: Override model (default from env or claude-sonnet-4-20250514)

    Returns:
        Response text or None on failure
    """
    client = get_claude_client()
    if not client:
        return None

    if not model:
        model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    if json_mode:
        system_instruction += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown fences, no explanation, no preamble. Just the JSON object."

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system_instruction,
            messages=[{"role": "user", "content": prompt}],
        )

        if response.content and len(response.content) > 0:
            text = response.content[0].text
            logger.info(f"Claude response: {len(text)} chars, model={model}")
            return text

        return None

    except Exception as e:
        logger.error(f"Claude API call failed: {e}")
        return None


def call_claude_for_analysis(
    document_text: str,
    analysis_type: str,
    context: dict = None,
) -> Optional[str]:
    """Specialized Claude call for different analysis types."""
    system_prompts = {
        "shred_rfp": """You are an elite government RFP analyst with 25 years of experience.
You extract EVERY requirement, evaluation factor, deadline, and compliance item from solicitation documents.
You never miss a single requirement. You understand FAR, DFAR, Section L, Section M, and all federal procurement regulations.
You are meticulous, thorough, and precise.""",
        "compliance_matrix": """You are a senior government proposal compliance director.
You map every RFP requirement to proposal sections and assess compliance status.
You've reviewed thousands of federal proposals and know exactly what evaluators look for.
You identify gaps before they cost the bid.""",
        "war_room": """You are an elite government capture strategist and competitive intelligence analyst.
You have 25+ years winning federal contracts worth billions.
You think like a chess grandmaster — always several moves ahead.
You are brutally honest about weaknesses and brilliant at finding winning strategies.
Your analysis is worth $10,000 in consulting fees.""",
        "proposal_review": """You are a senior government proposal reviewer and color team lead.
You evaluate proposals using Blue/Green/Yellow/Red team standards.
You've served on hundreds of federal evaluation panels.
You know exactly what wins and what loses. Be constructively critical.""",
        "opportunity_match": """You are a government business development strategist.
You match company capabilities to contract opportunities with precision.
You understand NAICS codes, set-asides, past performance requirements, and competitive positioning.""",
        "ghost_proposal": """You are a competitive intelligence analyst who creates ghost proposals.
You simulate what competitors would submit based on their known capabilities.
This helps your team understand the competition and craft winning counter-strategies.""",
        "pricing_strategy": """You are a government contract pricing strategist.
You analyze historical award data, market rates, and competitive dynamics
to recommend optimal pricing that maximizes win probability while protecting margins.""",
    }

    system = system_prompts.get(analysis_type, system_prompts["war_room"])

    token_limits = {
        "shred_rfp": 8000, "compliance_matrix": 8000, "war_room": 8000,
        "proposal_review": 6000, "opportunity_match": 2000,
        "ghost_proposal": 4000, "pricing_strategy": 4000,
    }

    max_tokens = token_limits.get(analysis_type, 6000)

    return call_claude(
        prompt=document_text,
        system_instruction=system,
        json_mode=True,
        max_tokens=max_tokens,
        temperature=0.2,
    )


# ─── Convenience Functions ────────────────────────────────

def smart_ai_call(
    prompt: str,
    system: str = "You are a helpful assistant.",
    json_mode: bool = True,
    max_tokens: int = 6000,
) -> Optional[str]:
    """
    Smart AI routing: Try Claude first (best quality), then Gemini (backup), then OpenAI.
    This triple-engine approach ensures SentriBiD always has AI available.
    """
    # 1. Try Claude (best reasoning, best for complex analysis)
    result = call_claude(prompt, system_instruction=system, json_mode=json_mode, max_tokens=max_tokens)
    if result:
        return result

    # 2. Try Gemini (good for long docs, cost-effective)
    try:
        from .gemini_ai import call_gemini
        result = call_gemini(prompt, system_instruction=system, json_mode=json_mode, max_tokens=max_tokens)
        if result:
            logger.info("Fell back to Gemini")
            return result
    except Exception:
        pass

    # 3. Try OpenAI (last resort)
    try:
        from .routers.opportunities import _call_openai
        result = _call_openai(system, prompt, json_mode=json_mode)
        if result:
            logger.info("Fell back to OpenAI")
            return result
    except Exception:
        pass

    logger.error("All AI engines failed")
    return None
