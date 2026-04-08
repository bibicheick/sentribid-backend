# backend/app/gemini_ai.py
"""
Google Gemini AI integration for SentriBiD.
Used primarily for proposal/document generation (longer outputs).
"""

import os
import json
import logging

logger = logging.getLogger("sentribid.gemini")


def get_gemini_client():
    """Initialize Gemini client. Returns None if not configured."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        return genai
    except ImportError:
        logger.warning("google-generativeai not installed. Run: pip install google-generativeai")
        return None
    except Exception as e:
        logger.error(f"Gemini init failed: {e}")
        return None


def call_gemini(prompt: str, system_instruction: str = "", json_mode: bool = False, max_tokens: int = 8000) -> str | None:
    """Call Gemini API for text generation.
    
    Args:
        prompt: The user prompt
        system_instruction: System-level instructions
        json_mode: If True, request JSON output
        max_tokens: Maximum output tokens (Gemini supports much larger outputs than GPT)
    
    Returns:
        Generated text or None on failure
    """
    genai = get_gemini_client()
    if not genai:
        return None

    try:
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        
        generation_config = {
            "temperature": 0.3,
            "max_output_tokens": max_tokens,
        }
        
        if json_mode:
            generation_config["response_mime_type"] = "application/json"

        model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction if system_instruction else None,
            generation_config=generation_config,
        )

        response = model.generate_content(prompt)
        
        if response and response.text:
            return response.text.strip()
        return None

    except Exception as e:
        logger.error(f"Gemini call failed: {e}")
        return None


def call_gemini_proposal(
    opportunity_context: str,
    analysis_context: str,
    profile_text: str,
    pricing_context: str = "",
    company_name: str = "Your Company",
) -> str | None:
    """Generate a complete proposal using Gemini (optimized for long-form output)."""
    
    system = f"""You are an expert government contract proposal writer for {company_name}.
You write winning proposals that are:
- Professional and compelling
- Specific to the solicitation requirements
- Rich with details from the company's actual capabilities
- Written in proper government contracting language
- Detailed enough to stand as a real submission draft

Always use the company name "{company_name}" throughout the proposal."""

    prompt = f"""Write a complete, professional government contract proposal response.

OPPORTUNITY DETAILS:
{opportunity_context}

AI ANALYSIS OF THIS OPPORTUNITY:
{analysis_context}

COMPANY PROFILE & CAPABILITIES:
{profile_text}

PRICING DATA:
{pricing_context if pricing_context else "No specific pricing available yet."}

Write the proposal with these sections. Each section should be 3-5 detailed paragraphs:

1. COVER LETTER
- Address to the contracting officer
- Reference the solicitation number
- Express interest and summarize qualifications
- Professional sign-off with company name

2. EXECUTIVE SUMMARY
- Why {company_name} is the best choice
- Key differentiators and relevant experience
- Understanding of the requirement
- Value proposition

3. TECHNICAL APPROACH
- Detailed methodology for delivering the work
- Specific to THIS solicitation's requirements
- Tools, technologies, and processes
- Timeline and milestones
- Innovation and efficiency

4. MANAGEMENT PLAN
- Project management methodology
- Team structure and reporting
- Communication plan with the agency
- Risk management approach
- Quality control processes

5. PAST PERFORMANCE
- Relevant contracts completed (use actual data from the company profile)
- Results and outcomes achieved
- Client satisfaction
- Similar scope and complexity

6. STAFFING PLAN
- Key personnel and their qualifications
- Team composition
- Certifications and clearances
- Staff retention and continuity

7. QUALITY ASSURANCE
- QA/QC methodology
- Performance metrics and KPIs
- Continuous improvement processes
- Compliance monitoring

8. PRICING NARRATIVE
- Pricing approach and methodology
- Value for money justification
- Cost efficiency measures
- Reference actual pricing if available

Make this proposal compelling, detailed, and ready for submission.
Use professional formatting with clear section headers."""

    return call_gemini(prompt, system_instruction=system, max_tokens=8000)
