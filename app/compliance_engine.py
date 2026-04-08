# backend/app/compliance_engine.py
"""
RFP Shredder & Compliance Matrix Engine for SentriBiD.
Uses Claude AI (primary) with Gemini/OpenAI fallback.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger("sentribid.compliance")


def _call_ai(system: str, prompt: str, json_mode: bool = True, max_tokens: int = 8000) -> str | None:
    """Smart AI routing: Claude → Gemini → OpenAI."""
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


def shred_rfp(document_text: str, opportunity_title: str = "") -> dict:
    """
    'Shred' an RFP — extract ALL structured information using Claude AI.
    """
    system = """You are an elite government RFP analyst with 25 years of federal procurement experience. 
You extract EVERY requirement, evaluation factor, deadline, and compliance item.
You never miss a single requirement. You understand FAR, DFAR, Section L, Section M.
You are meticulous, thorough, and precise. Return valid JSON only."""

    prompt = f"""Analyze this government solicitation and extract ALL structured information.

DOCUMENT TITLE: {opportunity_title}

FULL DOCUMENT TEXT:
{document_text[:30000]}

Return JSON:
{{
  "requirements": [
    {{"id": "REQ-001", "section": "Section reference", "requirement": "Full text", "type": "Technical|Management|Staffing|Past Performance|Pricing|Administrative", "mandatory": true/false}}
  ],
  "evaluation_factors": [
    {{"factor": "Name", "weight": "weight or priority", "description": "How evaluated", "subfactors": ["list"]}}
  ],
  "submission_format": {{
    "page_limit": null,
    "font_requirements": "",
    "sections_required": ["list"],
    "volumes": ["list"],
    "copies_required": "",
    "delivery_method": "",
    "delivery_address": ""
  }},
  "deadlines": [
    {{"event": "Name", "date": "date", "description": "details"}}
  ],
  "compliance_items": [
    {{"item": "Requirement", "regulation": "FAR/DFAR ref", "description": "What to demonstrate", "mandatory": true/false}}
  ],
  "forms_required": [
    {{"form_number": "SF-xxx", "form_name": "Title", "description": "Purpose"}}
  ],
  "key_personnel": [
    {{"role": "Title", "qualifications": "Required quals", "mandatory": true/false, "clearance": "If required"}}
  ],
  "set_aside_info": {{
    "type": "Type or None",
    "description": "Details",
    "certifications_needed": ["list"]
  }},
  "section_l_summary": "Instructions to offerors summary",
  "section_m_summary": "Evaluation criteria summary",
  "total_requirements_count": 0,
  "risk_flags": ["Unusual or risky requirements"]
}}

Be EXTREMELY thorough. Extract EVERY requirement."""

    result = _call_ai(system, prompt, json_mode=True, max_tokens=8000)
    if not result:
        return {"error": "AI analysis failed. Check your CLAUDE_API_KEY.", "requirements": []}

    try:
        return json.loads(_clean_json(result))
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse shredded RFP: {e}")
        return {"error": f"Parse error: {str(e)}", "raw_text": result[:2000], "requirements": []}


def generate_compliance_matrix(shredded_rfp: dict, company_profile: str, proposal_sections: list[str] | None = None) -> dict:
    """Generate compliance matrix mapping RFP requirements to proposal sections."""
    requirements = shredded_rfp.get("requirements", [])
    if not requirements:
        return {"error": "No requirements found. Shred the RFP first.", "matrix": []}

    reqs_text = json.dumps(requirements[:80], indent=1)

    system = """You are a government proposal compliance director with 20 years experience.
You map every RFP requirement to proposal sections and assess compliance gaps.
You know exactly what federal evaluators look for. Return valid JSON only."""

    prompt = f"""Generate a compliance matrix.

RFP REQUIREMENTS:
{reqs_text}

COMPANY CAPABILITIES:
{company_profile[:4000]}

{f'PROPOSED SECTIONS: {json.dumps(proposal_sections)}' if proposal_sections else ''}

Return JSON:
{{
  "matrix": [
    {{
      "req_id": "REQ-001",
      "requirement": "Short description",
      "rfp_section": "Original RFP section",
      "proposal_section": "Where to address this",
      "status": "Met|Partial|Gap|N/A",
      "response_approach": "How to respond",
      "risk_level": "Low|Medium|High",
      "notes": "Special considerations"
    }}
  ],
  "summary": {{"total": 0, "met": 0, "partial": 0, "gap": 0, "not_applicable": 0}},
  "compliance_score": 0,
  "critical_gaps": [
    {{"requirement": "...", "gap_description": "...", "mitigation": "How to address"}}
  ],
  "recommended_teaming": ["Capabilities to subcontract"],
  "proposal_outline": [
    {{"section": "Name", "description": "Content", "page_estimate": 0}}
  ]
}}"""

    result = _call_ai(system, prompt, json_mode=True, max_tokens=8000)
    if not result:
        return {"error": "AI compliance analysis failed", "matrix": []}

    try:
        return json.loads(_clean_json(result))
    except json.JSONDecodeError as e:
        return {"error": f"Parse error: {str(e)}", "matrix": []}


def review_proposal_against_rfp(proposal_text: str, shredded_rfp: dict, compliance_matrix: dict | None = None) -> dict:
    """Review a draft proposal against RFP requirements. Score using color team standards."""
    reqs_summary = ""
    if shredded_rfp.get("evaluation_factors"):
        reqs_summary = json.dumps(shredded_rfp["evaluation_factors"][:10])
    if shredded_rfp.get("requirements"):
        reqs_summary += "\n" + json.dumps(shredded_rfp["requirements"][:30])

    system = """You are a senior government proposal reviewer and color team lead.
You evaluate proposals using Blue/Green/Yellow/Red team standards.
You've served on hundreds of federal evaluation panels.
Be constructively critical — your goal is to help WIN. Return valid JSON only."""

    prompt = f"""Review this draft proposal against the RFP requirements.

RFP EVALUATION CRITERIA & REQUIREMENTS:
{reqs_summary[:6000]}

DRAFT PROPOSAL:
{proposal_text[:12000]}

Return JSON:
{{
  "overall_score": 0-100,
  "color_rating": "Blue|Green|Yellow|Red",
  "color_explanation": "What this means",
  "win_probability": 0-100,
  "section_scores": [
    {{
      "section": "Name",
      "score": 0-100,
      "color": "Blue|Green|Yellow|Red",
      "strengths": ["list"],
      "weaknesses": ["list"],
      "missing_requirements": ["REQ-xxx"],
      "suggestions": ["improvements"]
    }}
  ],
  "compliance_gaps": [{{"requirement": "...", "status": "Missing|Weak|Incomplete"}}],
  "priority_improvements": [
    {{"priority": 1, "action": "What to do", "impact": "High|Medium|Low", "effort": "Quick fix|Moderate|Major rewrite"}}
  ],
  "win_themes_present": ["found"],
  "win_themes_missing": ["should add"],
  "discriminators": ["what stands out or not"]
}}"""

    result = _call_ai(system, prompt, json_mode=True, max_tokens=6000)
    if not result:
        return {"error": "AI review failed", "overall_score": 0}

    try:
        return json.loads(_clean_json(result))
    except json.JSONDecodeError:
        return {"error": "Parse error", "overall_score": 0}
