# backend/app/win_predictor.py
"""
Win Predictor — AI War Room for SentriBiD.
The feature NO competitor has. Powered by Claude AI.
"""

import json
import logging

logger = logging.getLogger("sentribid.warroom")


def _call_ai(system: str, prompt: str, json_mode: bool = True, max_tokens: int = 8000) -> str | None:
    try:
        from .claude_ai import smart_ai_call
        return smart_ai_call(prompt, system=system, json_mode=json_mode, max_tokens=max_tokens)
    except Exception as e:
        logger.error(f"AI call failed: {e}")
        return None


def _clean_json(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    if clean.startswith("json"):
        clean = clean[4:].strip()
    return clean


def run_war_room(
    opportunity_context: str,
    company_profile: str,
    historical_awards: list[dict] | None = None,
    shredded_rfp: dict | None = None,
) -> dict:
    """
    Run the full AI War Room — SentriBiD's killer feature.
    
    Claude AI simulates the entire competitive landscape:
    1. Identifies likely competitors from historical data
    2. Analyzes each competitor's strengths/weaknesses
    3. Generates a 'ghost proposal' (what the best competitor would submit)
    4. Creates counter-strategies showing exactly how to beat them
    5. Recommends optimal pricing, win themes, and discriminators
    6. Produces win probability with confidence analysis
    """
    awards_context = ""
    if historical_awards:
        lines = []
        for a in historical_awards[:15]:
            lines.append(f"- {a.get('recipient', 'Unknown')}: ${a.get('amount', 0):,.0f} ({a.get('agency', '')}, {a.get('start_date', '')}-{a.get('end_date', '')})")
        awards_context = "\n".join(lines)

    rfp_context = ""
    if shredded_rfp:
        if shredded_rfp.get("evaluation_factors"):
            rfp_context += "EVALUATION FACTORS:\n" + json.dumps(shredded_rfp["evaluation_factors"][:8], indent=1)
        if shredded_rfp.get("requirements"):
            rfp_context += "\nKEY REQUIREMENTS:\n" + json.dumps(shredded_rfp["requirements"][:15], indent=1)

    system = """You are an elite government capture strategist and competitive intelligence analyst.
You have 25+ years winning federal contracts worth billions.
You think like a chess grandmaster — always several moves ahead.
You are brutally honest about weaknesses and brilliant at finding winning strategies.
Your analysis is worth $10,000 in consulting fees. Return valid JSON only."""

    prompt = f"""Run a COMPLETE competitive war room analysis.

OPPORTUNITY:
{opportunity_context[:6000]}

OUR COMPANY:
{company_profile[:4000]}

HISTORICAL AWARDS (similar contracts):
{awards_context or "No historical data — analyze based on market knowledge."}

{f'RFP ANALYSIS:{chr(10)}{rfp_context[:3000]}' if rfp_context else ''}

Return JSON:
{{
  "executive_brief": "2-3 sentence competitive position summary",
  "win_probability": {{
    "score": 0-100,
    "confidence": "High|Medium|Low",
    "key_factors": ["factors driving score"]
  }},
  "competitive_landscape": {{
    "likely_competitors": [
      {{
        "name": "Company name",
        "threat_level": "High|Medium|Low",
        "estimated_bid_range": "$X - $Y",
        "strengths": ["list"],
        "weaknesses": ["list"],
        "likely_strategy": "What they'll emphasize",
        "incumbent": true/false
      }}
    ],
    "total_expected_bidders": 0,
    "competitive_intensity": "High|Medium|Low"
  }},
  "ghost_proposal": {{
    "description": "What strongest competitor would submit",
    "technical_approach": "Their likely approach",
    "management_approach": "Their management plan",
    "pricing_strategy": "Their pricing approach",
    "key_differentiators": ["what they'd emphasize"],
    "weaknesses_to_exploit": ["vulnerabilities"]
  }},
  "our_win_strategy": {{
    "primary_win_themes": [
      {{"theme": "Name", "description": "How to articulate", "evidence": "Proof points"}}
    ],
    "technical_discriminators": [
      {{"discriminator": "What sets us apart", "impact": "Why evaluators care", "how_to_present": "Framing"}}
    ],
    "pricing_strategy": {{
      "approach": "Aggressive|Competitive|Value-based",
      "recommended_range": "$X - $Y",
      "reasoning": "Why this wins",
      "price_to_win": "$X"
    }},
    "proposal_focus_areas": [
      {{"section": "Name", "emphasis": "What to emphasize", "page_allocation": "Pages"}}
    ],
    "teaming_recommendations": [
      {{"capability_gap": "What we lack", "partner_type": "Sub type needed", "impact": "How it helps"}}
    ]
  }},
  "counter_strategies": [
    {{
      "if_competitor": "If [X] bids...",
      "their_likely_move": "They'll probably...",
      "our_counter": "We should...",
      "risk": "Low|Medium|High"
    }}
  ],
  "evaluation_playbook": {{
    "how_evaluators_think": "What panel prioritizes",
    "scoring_tips": ["maximize scores"],
    "common_mistakes": ["what loses points"],
    "oral_presentation_tips": ["if applicable"]
  }},
  "risk_assessment": [
    {{"risk": "Description", "probability": "H|M|L", "impact": "H|M|L", "mitigation": "How to address"}}
  ],
  "action_plan": [
    {{"priority": 1, "action": "Specific action", "owner": "Role", "deadline": "When", "impact": "Why"}}
  ],
  "bottom_line": "One paragraph — should we bid? How do we win?"
}}

Be specific, actionable, strategic. This should be worth $10,000."""

    result = _call_ai(system, prompt, json_mode=True, max_tokens=8000)
    if not result:
        return {"error": "AI war room analysis failed. Check CLAUDE_API_KEY.", "win_probability": {"score": 0}}

    try:
        return json.loads(_clean_json(result))
    except json.JSONDecodeError as e:
        return {"error": f"Parse error: {str(e)}", "raw_text": result[:3000], "win_probability": {"score": 0}}
