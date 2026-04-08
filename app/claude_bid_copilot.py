# backend/app/claude_bid_copilot.py
"""Claude AI Bid Copilot v0.7.0 — strategic pricing, win analysis, interactive chat"""
import os, json, logging
from typing import Optional

logger = logging.getLogger("sentribid.copilot")


def _get_api_key() -> str:
    """Get Claude/Anthropic API key — checks BOTH env vars."""
    return (
        os.getenv("CLAUDE_API_KEY", "").strip()
        or os.getenv("ANTHROPIC_API_KEY", "").strip()
    )


def _call_claude(system: str, user_msg: str, max_tokens: int = 2000) -> Optional[str]:
    """Call Claude API (Anthropic) for bid intelligence."""
    api_key = _get_api_key()
    if not api_key:
        logger.warning("Neither CLAUDE_API_KEY nor ANTHROPIC_API_KEY set")
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text
    except ImportError:
        logger.warning("anthropic package not installed, trying raw HTTP")
        return _call_claude_raw(api_key, system, user_msg, max_tokens)
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return None


def _call_claude_raw(api_key: str, system: str, user_msg: str, max_tokens: int) -> Optional[str]:
    """Fallback: call Claude via raw HTTP if anthropic package not installed."""
    try:
        import httpx
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user_msg}],
            },
            timeout=60,
        )
        data = resp.json()
        return data.get("content", [{}])[0].get("text", "")
    except Exception as e:
        logger.error(f"Claude raw HTTP error: {e}")
        return None


def analyze_bid_strategy(bid_data: dict, opp_data: dict, profile_data: dict, history: list) -> dict:
    """AI-powered bid strategy analysis with pricing recommendations."""
    system = """You are an expert government contracting bid strategist working for a small business.
Your job is to analyze an opportunity and recommend the optimal bid price with detailed reasoning.

You must respond in valid JSON with this structure:
{
  "recommended_price": <number>,
  "price_range": {"low": <number>, "high": <number>},
  "win_probability": <0-100>,
  "strategy": "<2-3 sentence strategy>",
  "pricing_rationale": "<detailed explanation of why this price>",
  "competitive_position": "<analysis of competitive landscape>",
  "risk_factors": ["<risk1>", "<risk2>"],
  "strengths_to_highlight": ["<strength1>", "<strength2>"],
  "key_differentiators": "<what sets you apart>",
  "price_breakdown": {
    "labor": <estimated>,
    "materials": <estimated>,
    "overhead": <estimated>,
    "profit_margin_pct": <recommended margin %>
  },
  "confidence": "<high/medium/low>",
  "reasoning_steps": ["<step1>", "<step2>", "<step3>"]
}"""

    context_parts = []

    if bid_data:
        context_parts.append(f"""BID DETAILS:
- Bid Code: {bid_data.get('bid_code', 'N/A')}
- Contract: {bid_data.get('contract_title', 'N/A')}
- Agency: {bid_data.get('agency_name', 'N/A')}
- Type: {bid_data.get('contract_type', 'service')}
- Risk Level: {bid_data.get('risk_level', 3)}/5
- Competition: {bid_data.get('competition_level', 'medium')}
- Deadline: {bid_data.get('deadline_date', 'N/A')}
- Notes: {bid_data.get('notes', '')[:500]}""")

    if opp_data:
        context_parts.append(f"""OPPORTUNITY ANALYSIS:
- Title: {opp_data.get('title', 'N/A')}
- NAICS: {opp_data.get('naics_code', 'N/A')}
- Set-Aside: {opp_data.get('set_aside', 'Open')}
- Value Range: ${opp_data.get('estimated_value_low', 0):,.0f} - ${opp_data.get('estimated_value_high', 0):,.0f}
- AI Summary: {opp_data.get('ai_summary', '')[:600]}
- AI Strategy: {opp_data.get('ai_bid_strategy', '')[:400]}
- AI Requirements: {opp_data.get('ai_requirements', '')[:400]}
- AI Risk Flags: {opp_data.get('ai_risk_flags', '')[:300]}""")

    if profile_data:
        context_parts.append(f"""YOUR COMPANY:
- Name: {profile_data.get('company_name', 'N/A')}
- Core Competencies: {profile_data.get('core_competencies', 'N/A')}
- Certifications: {profile_data.get('certifications', 'N/A')}
- Past Performance: {profile_data.get('past_performance', 'N/A')[:400]}
- Differentiators: {profile_data.get('differentiators', 'N/A')}
- Set-Aside Eligible: {profile_data.get('set_aside_eligible', 'N/A')}
- Annual Revenue: {profile_data.get('annual_revenue', 'N/A')}
- Employee Count: {profile_data.get('employee_count', 'N/A')}""")

    if history:
        context_parts.append("HISTORICAL BID DATA (past wins/losses):")
        for h in history[:10]:
            context_parts.append(f"- {h.get('contract_title', 'N/A')} | {h.get('agency_name', '')} | Status: {h.get('status', '')} | Risk: {h.get('risk_level', '')}")

    user_msg = "\n\n".join(context_parts)
    user_msg += "\n\nAnalyze this opportunity and provide your strategic bid recommendation in JSON format."

    result = _call_claude(system, user_msg, max_tokens=2500)
    if not result:
        return {"error": "Claude API call failed. Check CLAUDE_API_KEY or ANTHROPIC_API_KEY in .env."}

    try:
        cleaned = result.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"raw_response": result, "error": "Failed to parse JSON response"}


def copilot_chat(message: str, bid_data: dict, opp_data: dict, profile_data: dict,
                 chat_history: list, history: list) -> str:
    """Interactive chat with Claude about a specific bid."""
    system = f"""You are SentriBiD Copilot — an expert government contracting AI assistant.
You're helping analyze a specific bid and answering questions about it.

CURRENT BID: {json.dumps(bid_data, default=str)[:1500]}

OPPORTUNITY DATA: {json.dumps(opp_data, default=str)[:1500]}

COMPANY PROFILE: {json.dumps(profile_data, default=str)[:800]}

HISTORICAL BIDS: {json.dumps(history[:5], default=str)[:600]}

Guidelines:
- Be specific and actionable with pricing advice
- Reference the actual numbers from the bid data
- If asked about pricing, give concrete dollar amounts with reasoning
- If asked about risks, reference specific items from the RFP analysis
- Be concise but thorough — think like a capture manager
- When suggesting changes, explain the impact on win probability
- Always tie recommendations back to the evaluation criteria"""

    messages = []
    for msg in chat_history[-8:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": message})

    api_key = _get_api_key()
    if not api_key:
        return "Claude API key not configured. Add CLAUDE_API_KEY or ANTHROPIC_API_KEY to your .env file."

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except ImportError:
        return _call_claude_raw(api_key, system, message, 1500) or "Failed to reach Claude API."
    except Exception as e:
        logger.error(f"Copilot chat error: {e}")
        return f"Error: {str(e)}"
