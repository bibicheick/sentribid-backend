# backend/app/copilot.py
"""
SentriBiD AI Copilot Engine
----------------------------
Dual-mode: uses OpenAI GPT when OPENAI_API_KEY is set,
falls back to deterministic rule-based analysis otherwise.
"""

import os, json, logging
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("sentribid.copilot")

_openai_client = None

def _get_api_key():
    return os.getenv("OPENAI_API_KEY", "")

def _get_model():
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def _get_openai():
    global _openai_client
    key = _get_api_key()
    if not key:
        return None
    if _openai_client is None:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=key)
            print(f"  ✅ OpenAI initialized (model: {_get_model()})")
        except Exception as e:
            print(f"  ⚠️ OpenAI init failed: {e}")
            return None
    return _openai_client

def is_ai_enabled() -> bool:
    return bool(_get_api_key())

def _call_openai(system: str, user: str, json_mode: bool = True) -> Optional[str]:
    client = _get_openai()
    if not client:
        return None
    try:
        kwargs = {"model": _get_model(), "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.3, "max_tokens": 2000}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return None

def _bid_context_text(context: Dict[str, Any]) -> str:
    bid = context.get("bid", {})
    totals = context.get("totals", {})
    recs = context.get("recommendations", [])
    att = context.get("attachments_text", "")
    lines = [
        f"Bid Code: {bid.get('bid_code','N/A')}", f"Contract: {bid.get('contract_title','N/A')}",
        f"Agency: {bid.get('agency_name','N/A')} ({bid.get('agency_type','N/A')})",
        f"Contract Type: {bid.get('contract_type','N/A')}", f"Solicitation #: {bid.get('solicitation_number','N/A')}",
        f"Procurement: {bid.get('procurement_method','N/A')}", f"Risk: {bid.get('risk_level','N/A')}/5",
        f"Competition: {bid.get('competition_level','N/A')}", f"Urgency: {bid.get('urgency_level','N/A')}/5",
        f"Distance: {bid.get('delivery_distance_miles',0)} mi", f"Deadline: {bid.get('deadline_date','N/A')}",
        f"Status: {bid.get('status','N/A')}", f"Items: {bid.get('item_count',0)}, Labor lines: {bid.get('labor_count',0)}",
        "", "--- Costs ---",
        f"Items: ${totals.get('item_subtotal',0):,.2f}", f"Labor: ${totals.get('labor_total',0):,.2f}",
        f"Transport: ${totals.get('transport_total',0):,.2f}", f"Equipment: ${totals.get('equipment_total',0):,.2f}",
        f"Overhead: ${totals.get('overhead_total',0):,.2f}", f"True Cost: ${totals.get('true_cost',0):,.2f}",
        f"Risk Buffer: ${totals.get('risk_buffer',0):,.2f}", f"Adjusted Cost: ${totals.get('adjusted_cost',0):,.2f}",
    ]
    if recs:
        lines += ["", "--- Pricing Options ---"]
        for r in recs:
            lines.append(f"{r.get('mode','').upper()}: ${r.get('bid_price',0):,.2f} | Profit ${r.get('profit_amount',0):,.2f} | Margin {r.get('margin_pct',0):.1f}% | Win {r.get('win_score','N/A')}")
    if bid.get("notes"):
        lines.append(f"\nNotes: {bid['notes']}")
    if att:
        lines.append(f"\n--- Attached Documents ---\n{att[:3000]}")
    return "\n".join(lines)

def _days_until_deadline(d: Optional[str]) -> Optional[int]:
    if not d: return None
    try: return (datetime.strptime(str(d)[:10], "%Y-%m-%d").date() - date.today()).days
    except: return None

# ═══════════════════ RISK ═══════════════════

def analyze_bid_risk(context: Dict[str, Any]) -> Dict[str, Any]:
    if is_ai_enabled():
        r = _call_openai(
            """You are a government bid risk analyst. Return JSON: {"overall_risk_score":<0-100>,"risk_grade":"<A-F>","items":[{"category":"","severity":"<low/medium/high/critical>","title":"","detail":"","recommendation":""}],"summary":""}. Consider: deadline, competition, costs, agency type, logistics, attached docs.""",
            f"Analyze risks:\n\n{_bid_context_text(context)}")
        if r:
            try: return json.loads(r)
            except: pass
    # Rule fallback
    bid, totals, items, score = context.get("bid",{}), context.get("totals",{}), [], 20
    rl = bid.get("risk_level",1)
    if rl >= 4: items.append({"category":"Risk Rating","severity":"high","title":f"High risk ({rl}/5)","detail":"Elevated risk. Higher buffers recommended.","recommendation":"Increase risk buffer and insurance."}); score += 25
    elif rl >= 3: items.append({"category":"Risk Rating","severity":"medium","title":f"Moderate risk ({rl}/5)","detail":"Standard profile. Monitor cost drivers.","recommendation":"Review transport and labor estimates."}); score += 12
    comp = bid.get("competition_level","medium")
    if comp == "high": items.append({"category":"Competition","severity":"high","title":"High competition","detail":"Significant pricing pressure expected.","recommendation":"Use conservative pricing."}); score += 18
    dl = _days_until_deadline(bid.get("deadline_date"))
    if dl is not None and dl < 5: items.append({"category":"Timeline","severity":"critical","title":f"Deadline in {dl}d","detail":"Very tight timeline.","recommendation":"Prioritize immediately."}); score += 20
    elif dl is not None and dl < 14: items.append({"category":"Timeline","severity":"medium","title":f"Deadline in {dl}d","detail":"Moderate timeline.","recommendation":"Lock down quotes."}); score += 8
    if totals.get("true_cost",0) == 0: items.append({"category":"Costs","severity":"critical","title":"No cost data","detail":"True cost is $0.","recommendation":"Add all cost components."}); score += 20
    if bid.get("item_count",0) == 0: items.append({"category":"Items","severity":"medium","title":"No line items","detail":"Most contracts require itemized costs.","recommendation":"Add items."}); score += 8
    score = min(score, 100)
    grade = "A" if score <= 25 else "B" if score <= 40 else "C" if score <= 60 else "D" if score <= 80 else "F"
    if not items: items.append({"category":"Overall","severity":"low","title":"Low risk","detail":"No significant risks.","recommendation":"Proceed normally."})
    return {"overall_risk_score":score,"risk_grade":grade,"items":items,"summary":f"Risk {score}/100 (Grade {grade}). {len(items)} factor(s)."}

# ═══════════════════ PROFIT ═══════════════════

def analyze_bid_profit(context: Dict[str, Any]) -> Dict[str, Any]:
    if is_ai_enabled():
        r = _call_openai(
            """Government bid profit consultant. Return JSON: {"current_margin_assessment":"","suggestions":[{"strategy":"","description":"","estimated_impact_pct":<float>,"confidence":"<low/medium/high>","priority":<int>}],"optimal_mode":"<conservative/balanced/aggressive>","summary":""}""",
            f"Optimize profit:\n\n{_bid_context_text(context)}")
        if r:
            try: return json.loads(r)
            except: pass
    # Rule fallback
    bid, totals, sugs, p = context.get("bid",{}), context.get("totals",{}), [], 1
    tc = totals.get("true_cost",0) or 1
    if totals.get("item_subtotal",0)/tc > 0.6: sugs.append({"strategy":"Material Negotiation","description":f"Materials are {totals['item_subtotal']/tc*100:.0f}% of costs. Negotiate bulk pricing.","estimated_impact_pct":2.5,"confidence":"medium","priority":p}); p+=1
    if totals.get("labor_total",0)/tc > 0.3: sugs.append({"strategy":"Labor Optimization","description":f"Labor is {totals['labor_total']/tc*100:.0f}% of costs.","estimated_impact_pct":1.5,"confidence":"medium","priority":p}); p+=1
    if totals.get("transport_total",0) > 500: sugs.append({"strategy":"Logistics Savings","description":"Consolidate deliveries.","estimated_impact_pct":1.0,"confidence":"low","priority":p}); p+=1
    if not sugs: sugs.append({"strategy":"Maintain Approach","description":"Cost structure is reasonable.","estimated_impact_pct":0,"confidence":"high","priority":1})
    comp = bid.get("competition_level","medium")
    opt = "balanced" if comp == "medium" else "conservative" if comp == "high" else "aggressive"
    bm = context.get("base_margin_pct",10)
    return {"current_margin_assessment":f"Base margin: {bm:.1f}%.","suggestions":sugs,"optimal_mode":opt,"summary":f"{len(sugs)} strategies. Recommended: {opt}."}

# ═══════════════════ COMPLIANCE ═══════════════════

def analyze_bid_compliance(context: Dict[str, Any]) -> Dict[str, Any]:
    if is_ai_enabled():
        r = _call_openai(
            """Government contracting compliance expert. Return JSON: {"overall_status":"<compliant/needs_review/non_compliant>","flags":[{"rule":"","status":"<pass/warning/fail>","detail":"","action_required":""}],"summary":""}""",
            f"Check compliance:\n\n{_bid_context_text(context)}")
        if r:
            try: return json.loads(r)
            except: pass
    # Rule fallback
    bid, totals, flags = context.get("bid",{}), context.get("totals",{}), []
    sol = bid.get("solicitation_number","")
    flags.append({"rule":"Solicitation #","status":"pass" if sol else "fail","detail":f"#{sol}" if sol else "Missing.","action_required":"None" if sol else "Add solicitation number."})
    proc = bid.get("procurement_method","")
    flags.append({"rule":"Procurement Method","status":"pass" if proc else "warning","detail":f"{proc.upper()}" if proc else "Not set.","action_required":"None" if proc else "Set procurement method."})
    flags.append({"rule":"Itemized Pricing","status":"pass" if bid.get("item_count",0) > 0 else "warning","detail":f"{bid.get('item_count',0)} items." if bid.get("item_count",0) else "No items.","action_required":"None" if bid.get("item_count",0) else "Add line items."})
    dl = _days_until_deadline(bid.get("deadline_date"))
    if dl is not None and dl < 0: flags.append({"rule":"Deadline","status":"fail","detail":"Passed.","action_required":"Verify deadline."})
    elif dl is not None and dl < 3: flags.append({"rule":"Deadline","status":"warning","detail":f"{dl}d left.","action_required":"Expedite."})
    else: flags.append({"rule":"Deadline","status":"pass","detail":"Feasible.","action_required":"None"})
    if bid.get("agency_type") == "federal": flags.append({"rule":"FAR Compliance","status":"warning","detail":"Federal contract.","action_required":"Review FAR clauses."})
    if totals.get("true_cost",0) > 250000: flags.append({"rule":"Bonding","status":"warning","detail":f"Cost ${totals['true_cost']:,.0f} may need bonding.","action_required":"Check bonding requirements."})
    hf = any(f["status"]=="fail" for f in flags)
    hw = any(f["status"]=="warning" for f in flags)
    ov = "non_compliant" if hf else "needs_review" if hw else "compliant"
    fc = sum(1 for f in flags if f["status"]=="fail")
    wc = sum(1 for f in flags if f["status"]=="warning")
    return {"overall_status":ov,"flags":flags,"summary":f"{ov.replace('_',' ').title()}. {fc} issue(s), {wc} warning(s)."}

# ═══════════════════ CHAT ═══════════════════

def chat_with_copilot(message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    if is_ai_enabled():
        ctx_text = _bid_context_text(context)
        r = _call_openai(
            f"""You are SentriBiD's AI Copilot for government bids. You have this bid data:\n\n{ctx_text}\n\nAnswer questions with specific numbers. Be concise (3-5 paragraphs max). Return JSON: {{"reply":"<response>","suggestions":["q1","q2","q3"]}}""",
            message)
        if r:
            try: return json.loads(r)
            except: pass
    # Rule fallback
    msg = message.lower().strip()
    bid_code = context.get("bid_code","this bid")
    totals = context.get("totals",{})
    tc = totals.get("true_cost",0)
    sug = ["What's my risk exposure?","How can I improve margins?","Is pricing competitive?","What should I do next?"]
    if any(w in msg for w in ["cost","total","price","budget"]):
        return {"reply":f"Costs for {bid_code}: Items ${totals.get('item_subtotal',0):,.2f}, Labor ${totals.get('labor_total',0):,.2f}, Transport ${totals.get('transport_total',0):,.2f}, Equipment ${totals.get('equipment_total',0):,.2f}, Overhead ${totals.get('overhead_total',0):,.2f}. True Cost: ${tc:,.2f}.","suggestions":sug}
    if any(w in msg for w in ["risk","danger","concern"]):
        rl = context.get("risk_level",1)
        return {"reply":f"Risk level: {rl}/5. {'High — increase buffers.' if rl>=4 else 'Moderate — monitor closely.' if rl>=3 else 'Low — favorable.'}","suggestions":sug}
    if any(w in msg for w in ["compet","win","chance"]):
        c = context.get("competition_level","medium")
        return {"reply":{"high":"High competition — conservative pricing recommended.","low":"Low competition — aggressive pricing opportunity.","medium":"Medium competition — balanced mode optimal."}.get(c,"Balanced mode recommended."),"suggestions":sug}
    if any(w in msg for w in ["next","step","todo","action"]):
        s = context.get("status","draft")
        return {"reply":"Add cost data then compute pricing." if s=="draft" and tc==0 else "Review recommendations and approve." if s=="draft" else "Export and submit your proposal.","suggestions":sug}
    return {"reply":f"I'm your Copilot for {bid_code}. Ask about costs, risks, competition, compliance, or next steps.","suggestions":sug}

# ═══════════════════ PORTFOLIO ═══════════════════

def portfolio_insights(bids: List[Dict[str, Any]]) -> Dict[str, Any]:
    if is_ai_enabled() and bids:
        summ = [f"- {b.get('bid_code')}: {b.get('contract_title')} | {b.get('agency_name')} | Risk {b.get('risk_level',0)}/5 | {b.get('status')} | Deadline: {b.get('deadline_date','N/A')}" for b in bids[:20]]
        r = _call_openai(
            """Bid portfolio analyst. Return JSON: {"total_bids":<int>,"draft_count":<int>,"approved_count":<int>,"avg_risk":<float>,"high_risk_bids":[{"bid_code":"","contract_title":"","risk_level":0}],"urgent_bids":[],"agency_distribution":{},"recommendations":[""],"summary":""}""",
            f"Analyze portfolio ({len(bids)} bids):\n\n" + "\n".join(summ))
        if r:
            try: return json.loads(r)
            except: pass
    # Rule fallback
    total = len(bids)
    if total == 0: return {"total_bids":0,"draft_count":0,"approved_count":0,"avg_risk":0,"high_risk_bids":[],"recommendations":["Create your first bid."],"summary":"No bids yet."}
    dc = sum(1 for b in bids if (b.get("status") or "").lower()=="draft")
    ac = sum(1 for b in bids if (b.get("status") or "").lower()=="approved")
    ar = sum(b.get("risk_level",1) for b in bids)/total
    hr = [{"bid_code":b["bid_code"],"contract_title":b["contract_title"],"risk_level":b["risk_level"]} for b in bids if b.get("risk_level",1)>=4]
    urg = [b["bid_code"] for b in bids if (d:=_days_until_deadline(b.get("deadline_date"))) is not None and 0<=d<=7 and (b.get("status") or "").lower()=="draft"]
    recs = []
    if dc: recs.append(f"{dc} draft bid(s) — review before deadlines.")
    if hr: recs.append(f"{len(hr)} high-risk bid(s).")
    if urg: recs.append(f"Urgent: {', '.join(urg)} due within 7 days.")
    if not recs: recs.append("Portfolio looks healthy.")
    at = {}
    for b in bids: at[b.get("agency_type","unknown")] = at.get(b.get("agency_type","unknown"),0)+1
    return {"total_bids":total,"draft_count":dc,"approved_count":ac,"avg_risk":round(ar,1),"high_risk_bids":hr,"urgent_bids":urg,"agency_distribution":at,"recommendations":recs,"summary":f"{total} bids: {dc} draft, {ac} approved. Avg risk: {ar:.1f}/5."}
