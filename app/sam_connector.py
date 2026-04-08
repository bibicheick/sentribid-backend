# backend/app/sam_connector.py
"""
SAM.gov API Connector + USAspending Intelligence for SentriBiD.
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("sentribid.sam")

SAM_BASE_URL = "https://api.sam.gov/prod/opportunities/v2/search"
USASPENDING_BASE_URL = "https://api.usaspending.gov/api/v2"

_cache = {}
CACHE_TTL = 3600


def _cache_key(params: dict) -> str:
    return hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()


def _get_cached(key: str):
    if key in _cache:
        entry = _cache[key]
        if datetime.now().timestamp() - entry["ts"] < CACHE_TTL:
            return entry["data"]
    return None


def _set_cached(key: str, data):
    _cache[key] = {"data": data, "ts": datetime.now().timestamp()}


def get_sam_api_key() -> str:
    return os.getenv("SAM_GOV_API_KEY", "")


def search_opportunities(
    keyword: str = "",
    naics_code: str = "",
    set_aside: str = "",
    agency: str = "",
    posted_from: str = "",
    posted_to: str = "",
    opportunity_type: str = "",
    limit: int = 25,
    offset: int = 0,
    sort_by: str = "-postedDate",
) -> dict:
    """Search SAM.gov for contract opportunities."""
    import requests

    api_key = get_sam_api_key()
    if not api_key:
        return {"total": 0, "opportunities": [], "error": "SAM_GOV_API_KEY not configured in .env", "cached": False}

    if not posted_from:
        posted_from = (datetime.now() - timedelta(days=90)).strftime("%m/%d/%Y")
    if not posted_to:
        posted_to = datetime.now().strftime("%m/%d/%Y")

    params = {
        "api_key": api_key,
        "limit": min(limit, 100),
        "offset": offset,
        "postedFrom": posted_from,
        "postedTo": posted_to,
    }

    if keyword:
        params["title"] = keyword
    if naics_code:
        params["ncode"] = naics_code
    if set_aside:
        params["typeOfSetAside"] = set_aside
    if agency:
        params["deptname"] = agency
    if opportunity_type:
        params["ptype"] = opportunity_type

    ck = _cache_key(params)
    cached = _get_cached(ck)
    if cached:
        return {**cached, "cached": True}

    try:
        resp = requests.get(SAM_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        total = data.get("totalRecords", 0)
        raw_opps = data.get("opportunitiesData", [])

        opportunities = [normalize_sam_opportunity(r) for r in raw_opps]

        result = {"total": total, "opportunities": opportunities, "error": None}
        _set_cached(ck, result)
        return {**result, "cached": False}

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else 0
        if status == 429:
            return {"total": 0, "opportunities": [], "error": "SAM.gov rate limit exceeded. Try again later.", "cached": False}
        elif status == 403:
            return {"total": 0, "opportunities": [], "error": "SAM.gov API key invalid. Check SAM_GOV_API_KEY in .env", "cached": False}
        return {"total": 0, "opportunities": [], "error": f"SAM.gov error: {status}", "cached": False}
    except Exception as e:
        logger.error(f"SAM.gov search failed: {e}")
        return {"total": 0, "opportunities": [], "error": str(e), "cached": False}


def normalize_sam_opportunity(raw: dict) -> dict:
    """Convert SAM.gov API response to SentriBiD format."""
    contacts = raw.get("pointOfContact", [])
    primary = contacts[0] if contacts else {}

    award = raw.get("award", {})
    award_amount = award.get("amount") if award else None
    awardee_name = award.get("awardee", {}).get("name") if award else None

    return {
        "sam_notice_id": raw.get("noticeId", ""),
        "title": raw.get("title", "Untitled"),
        "solicitation_number": raw.get("solicitationNumber", "").strip(),
        "agency_name": raw.get("fullParentPathName") or raw.get("department") or raw.get("subTier") or "Unknown",
        "department": raw.get("department", ""),
        "sub_tier": raw.get("subTier", ""),
        "office": raw.get("office", ""),
        "posted_date": raw.get("postedDate", ""),
        "due_date": raw.get("responseDeadLine", ""),
        "type": raw.get("type", ""),
        "base_type": raw.get("baseType", ""),
        "naics_code": raw.get("naicsCode", ""),
        "classification_code": raw.get("classificationCode", ""),
        "set_aside": raw.get("typeOfSetAside", ""),
        "set_aside_description": raw.get("typeOfSetAsideDescription", ""),
        "active": raw.get("active", "Yes"),
        "description_url": raw.get("uiLink") or f"https://sam.gov/opp/{raw.get('noticeId', '')}/view",
        "resource_links": raw.get("resourceLinks", []),
        "contact_name": f"{primary.get('firstName', '')} {primary.get('lastName', '')}".strip(),
        "contact_email": primary.get("email", ""),
        "contact_phone": primary.get("phone", ""),
        "award_amount": award_amount,
        "awardee_name": awardee_name,
    }


def search_awards(keyword: str = "", naics_code: str = "", agency: str = "", limit: int = 10) -> dict:
    """Search USAspending.gov for historical awards (competitive intel)."""
    import requests

    try:
        filters = {"time_period": [{"start_date": "2020-01-01", "end_date": datetime.now().strftime("%Y-%m-%d")}]}
        if keyword:
            filters["keywords"] = [keyword]
        if naics_code:
            filters["naics_codes"] = [{"naics_code": naics_code, "is_primary": True}]
        if agency:
            filters["agencies"] = [{"type": "awarding", "name": agency}]

        payload = {
            "filters": filters,
            "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency", "Start Date", "End Date", "Description", "NAICS Code"],
            "limit": limit,
            "page": 1,
            "sort": "Award Amount",
            "order": "desc",
        }

        resp = requests.post(f"{USASPENDING_BASE_URL}/search/spending_by_award/", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        awards = []
        for r in data.get("results", []):
            awards.append({
                "award_id": r.get("Award ID", ""),
                "recipient": r.get("Recipient Name", ""),
                "amount": r.get("Award Amount"),
                "agency": r.get("Awarding Agency", ""),
                "start_date": r.get("Start Date", ""),
                "end_date": r.get("End Date", ""),
                "description": r.get("Description", ""),
                "naics": r.get("NAICS Code", ""),
            })

        return {"total": data.get("page_metadata", {}).get("total", 0), "awards": awards, "error": None}

    except Exception as e:
        logger.error(f"USAspending search failed: {e}")
        return {"total": 0, "awards": [], "error": str(e)}


def score_opportunity_fit(opportunity: dict, profile_text: str) -> dict:
    """Use Claude AI to score opportunity fit against business profile."""
    try:
        from .claude_ai import smart_ai_call
    except ImportError:
        return {"fit_score": 0, "recommendation": "UNKNOWN", "match_reasons": [], "gaps": ["AI unavailable"]}

    opp_text = f"Title: {opportunity.get('title')}\nAgency: {opportunity.get('agency_name')}\nNAICS: {opportunity.get('naics_code')}\nSet-Aside: {opportunity.get('set_aside_description') or 'None'}\nType: {opportunity.get('type')}\nDue: {opportunity.get('due_date')}"

    prompt = f"""Score this opportunity match. OPPORTUNITY:\n{opp_text}\n\nCOMPANY:\n{profile_text}\n\nReturn JSON:\n{{"fit_score": 0-100, "recommendation": "BID|SKIP|CONDITIONAL", "match_reasons": ["r1","r2","r3"], "gaps": ["g1"], "suggested_action": "one sentence"}}"""

    result = smart_ai_call(prompt, system="You are a government BD strategist. Score accurately.", json_mode=True, max_tokens=1500)
    if result:
        try:
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1]
            if clean.endswith("```"):
                clean = clean[:-3]
            if clean.strip().startswith("json"):
                clean = clean.strip()[4:]
            return json.loads(clean.strip())
        except Exception:
            pass

    return {"fit_score": 0, "recommendation": "UNKNOWN", "match_reasons": [], "gaps": ["AI scoring failed"]}
