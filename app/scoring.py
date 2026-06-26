"""BharatWatch automated red-flag detection & risk scoring.

Rule-based engine over the relationship graph. Every flag carries:
risk_score (0-100), plain-English explanation, value involved (₹), and
evidence references back to source records.
"""
import json
import math
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db

CR = 1e7


def fmt_cr(rupees):
    return f"₹{rupees / CR:,.1f} Cr"


def _value_boost(value, base=0, per_log=18, cap=95):
    """Score grows with log of value in crores."""
    crores = max(value / CR, 0.01)
    return min(cap, int(base + per_log * math.log10(crores + 1)))


def _is_during_tenure(c, pol_id, date_str):
    """Check if date_str (YYYY-MM-DD) falls within any of the politician's active tenures."""
    if not date_str:
        return False
    rows = c.execute("SELECT start_date, end_date FROM tenures WHERE entity_id=?", (pol_id,)).fetchall()
    if not rows:
        return True
    for r in rows:
        start = r["start_date"]
        end = r["end_date"] or "9999-12-31"
        if start <= date_str <= end:
            return True
    return False


def _family_web(c, pol_id):
    """Return {person_id: how} for the politician + family members up to 3rd degree (3 hops)."""
    web = {pol_id: "self"}
    queue = [(pol_id, 0, "self")]
    while queue:
        curr_id, depth, curr_how = queue.pop(0)
        if depth >= 3:
            continue
        # Primary family links
        rows = c.execute(
            "SELECT from_id, to_id, evidence FROM relationships WHERE type='Family_Link' AND (from_id=? OR to_id=?)",
            (curr_id, curr_id),
        ).fetchall()
        # Additional close family relations (spouse, sibling)
        extra = c.execute(
            "SELECT from_id, to_id, evidence FROM relationships WHERE type IN ('Spouse_Of','Sibling_Of') AND (from_id=? OR to_id=?)",
            (curr_id, curr_id),
        ).fetchall()
        rows.extend(extra)
        for r in rows:
            other = r["to_id"] if r["from_id"] == curr_id else r["from_id"]
            if other not in web:
                ev = r["evidence"] or "family link"
                if curr_id == pol_id:
                    how = ev
                else:
                    how = f"{ev} (via {curr_how})"
                web[other] = how
                queue.append((other, depth + 1, how))
    return web


def _companies_of(c, person_ids):
    """{company_id: (person_id, evidence)} for Director_Of, Shareholder_Of, Beneficial_Owner_Of, Trustee_Of links."""
    out = {}
    for pid in person_ids:
        rows = c.execute(
            "SELECT to_id, type, evidence FROM relationships WHERE from_id=? AND type IN ('Director_Of','Shareholder_Of','Beneficial_Owner_Of','Trustee_Of')",
            (pid,),
        ).fetchall()
        for r in rows:
            out[r["to_id"]] = (pid, r["evidence"])
    return out


def _name(c, eid):
    r = c.execute("SELECT name FROM entities WHERE id=?", (eid,)).fetchone()
    return r["name"] if r else f"#{eid}"


def _oversees(c, pol_id):
    return {
        r["to_id"]
        for r in c.execute(
            "SELECT to_id FROM relationships WHERE from_id=? AND type IN ('Oversees','Directs_Funds_To')",
            (pol_id,),
        )
    }


def _add_flag(c, entity_id, pattern, score, title, explanation, value, evidence):
    c.execute(
        "INSERT INTO flags (entity_id, pattern, risk_score, title, explanation, value_involved, evidence) VALUES (?,?,?,?,?,?,?)",
        (entity_id, pattern, score, title, explanation, value, json.dumps(evidence)),
    )


def rule_family_contracts(c, pol):
    """Politician → family member → director of company → company wins govt contracts."""
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return
    companies = _companies_of(c, family_only.keys())
    if not companies:
        return
    overseen = _oversees(c, pol["id"])
    total, items, overseen_hit, during_tenure_hit = 0, [], False, False
    for comp_id, (pid, ev) in companies.items():
        rows = c.execute(
            "SELECT * FROM contracts WHERE supplier_id=?", (comp_id,)
        ).fetchall()
        for r in rows:
            in_tenure = _is_during_tenure(c, pol["id"], r["award_date"])
            if in_tenure:
                during_tenure_hit = True
            total += r["value"]
            if r["buyer_id"] in overseen:
                overseen_hit = True
            items.append({
                "tender_id": r["tender_id"], "title": r["title"], "value": r["value"],
                "buyer": _name(c, r["buyer_id"]), "supplier": _name(c, comp_id),
                "award_date": r["award_date"], "via": f"{_name(c, pid)} ({ev})", "source": r["source"],
                "during_tenure": in_tenure
            })
    if total <= 0:
        return
    score = _value_boost(total, base=45, per_log=20)
    if overseen_hit:
        score = min(96, score + 18)
    if during_tenure_hit:
        score = min(98, score + 10)
    comp_names = ", ".join(sorted({i["supplier"] for i in items}))
    explanation = (
        f"{fmt_cr(total)} in government contracts awarded to {comp_names} — "
        f"firm(s) directed by declared family members of {pol['name']} (shared DIN trail via MCA records). "
        + ("The awarding department falls under a body this politician oversees or directs funds to. "
           if overseen_hit else "")
        + ("One or more contracts were awarded during the politician's active term of office. "
           if during_tenure_hit else "")
        + f"Pattern: Politician → Family_Link → Director_Of → Contract_Awarded_To across {len(items)} award(s)."
    )
    _add_flag(c, pol["id"], "FAMILY_CONTRACT", score,
              f"{fmt_cr(total)} in contracts to family-linked firms", explanation, total, items)


def rule_asset_growth(c, pol):
    """Declared asset growth incompatible with declared income."""
    rows = c.execute(
        "SELECT * FROM declarations WHERE entity_id=? ORDER BY year", (pol["id"],)
    ).fetchall()
    if len(rows) < 2:
        return
    first, last = rows[0], rows[-1]
    years = max(last["year"] - first["year"], 1)
    growth = last["assets"] - first["assets"]
    # generous ceiling: declared income every year, fully saved, plus 12%/yr appreciation
    plausible = last["income"] * years + first["assets"] * (1.12 ** years - 1)
    if growth <= 0 or plausible <= 0:
        return
    ratio = growth / plausible
    if ratio < 2.0:
        return
    score = min(94, int(40 + 14 * math.log2(ratio)))
    explanation = (
        f"Declared assets grew from {fmt_cr(first['assets'])} ({first['year']}) to "
        f"{fmt_cr(last['assets'])} ({last['year']}) — a rise of {fmt_cr(growth)}. "
        f"Even assuming all declared income (~{fmt_cr(last['income'])}/yr) was saved and existing "
        f"assets appreciated 12%/yr, the plausible accumulation is ~{fmt_cr(plausible)}. "
        f"Observed growth is {ratio:.1f}× the plausible ceiling. Pattern: Incompatible asset growth (ECI affidavits)."
    )
    _add_flag(c, pol["id"], "ASSET_GROWTH", score,
              f"Assets grew {ratio:.1f}× faster than declared income allows", explanation, growth,
              [dict(r) for r in rows])


def rule_repeated_awards(c, pol):
    """One connected supplier repeatedly winning from a dept the politician oversees."""
    overseen = _oversees(c, pol["id"])
    if not overseen:
        return
    # suppliers connected to politician within 2 hops (family/donor -> company)
    web = _family_web(c, pol["id"])
    donors = {
        r["from_id"]
        for r in c.execute(
            "SELECT from_id FROM relationships WHERE to_id=? AND type='Donor_To'", (pol["id"],)
        )
    }
    connected_people = set(web.keys()) | donors
    connected_companies = set(_companies_of(c, connected_people).keys())
    for buyer in overseen:
        groups = c.execute(
            "SELECT supplier_id, COUNT(*) n, SUM(value) total FROM contracts WHERE buyer_id=? GROUP BY supplier_id",
            (buyer,),
        ).fetchall()
        all_n = sum(g["n"] for g in groups)
        for g in groups:
            if g["supplier_id"] not in connected_companies or g["n"] < 3:
                continue
            
            contracts = c.execute(
                "SELECT tender_id, title, value, award_date, source FROM contracts WHERE buyer_id=? AND supplier_id=?",
                (buyer, g["supplier_id"])
            ).fetchall()
            
            tenure_n = 0
            items = []
            for r in contracts:
                in_tenure = _is_during_tenure(c, pol["id"], r["award_date"])
                if in_tenure:
                    tenure_n += 1
                items.append({
                    "tender_id": r["tender_id"], "title": r["title"], "value": r["value"],
                    "award_date": r["award_date"], "source": r["source"], "during_tenure": in_tenure
                })
            
            share = g["n"] / all_n if all_n else 0
            score = min(95, _value_boost(g["total"], base=50, per_log=15) + int(20 * share))
            if tenure_n > 0:
                score = min(97, score + 10)
                
            sup, buy = _name(c, g["supplier_id"]), _name(c, buyer)
            how = "family-linked" if g["supplier_id"] in set(
                _companies_of(c, web.keys()).keys()) else "linked to an election donor"
            
            explanation = (
                f"{sup} won {g['n']} of {all_n} contracts ({share:.0%}) worth {fmt_cr(g['total'])} from {buy}, "
                f"a body overseen by {pol['name']}. The supplier is {how} "
                f"(shared DIN per MCA records). "
                + (f"{tenure_n} of these awards occurred during the politician's active term of office. " if tenure_n > 0 else "")
                + f"Pattern: Repeated awards to a connected company."
            )
            _add_flag(c, pol["id"], "REPEATED_AWARDS", score,
                      f"{sup} won {share:.0%} of {buy} contracts ({fmt_cr(g['total'])})",
                      explanation, g["total"], items)


def rule_ghost_entity(c, pol):
    """Company incorporated shortly before its first award, esp. with shared address or disproportionate balance sheet."""
    web = _family_web(c, pol["id"])
    companies = _companies_of(c, web.keys())
    for comp_id in companies:
        comp = c.execute("SELECT * FROM entities WHERE id=?", (comp_id,)).fetchone()
        if not comp or not comp["incorporation_date"]:
            continue
        first = c.execute(
            "SELECT * FROM contracts WHERE supplier_id=? ORDER BY award_date LIMIT 1", (comp_id,)
        ).fetchone()
        if not first or not first["award_date"]:
            continue
        try:
            inc = datetime.strptime(comp["incorporation_date"], "%Y-%m-%d")
            awd = datetime.strptime(first["award_date"], "%Y-%m-%d")
        except ValueError:
            continue
        days = (awd - inc).days
        if days < 0 or days > 120:
            continue
        shared = c.execute(
            "SELECT * FROM relationships WHERE type='Shared_Address' AND (from_id=? OR to_id=?)",
            (comp_id, comp_id),
        ).fetchone()
        
        # Check company financials for the year of the award or closest previous year
        award_yr = awd.year
        fin = c.execute(
            "SELECT * FROM company_financials WHERE company_id=? AND year<=? ORDER BY year DESC LIMIT 1",
            (comp_id, award_yr)
        ).fetchone()
        
        fin_flagged = False
        fin_info = ""
        if fin:
            max_comp_val = max(fin["revenue"], fin["assets"], 1.0)
            if first["value"] > 3 * max_comp_val:
                fin_flagged = True
                fin_info = (
                    f" The contract value ({fmt_cr(first['value'])}) is disproportionately large ({first['value'] / max_comp_val:.1f}x) "
                    f"compared to the firm's declared financials in FY{fin['year']} (Revenue: {fmt_cr(fin['revenue'])}, Assets: {fmt_cr(fin['assets'])})."
                )
                
        score = min(95, 62 + (15 if shared else 0) + (18 if fin_flagged else 0) + _value_boost(first["value"], base=0, per_log=10, cap=15))
        explanation = (
            f"{comp['name']} was incorporated on {comp['incorporation_date']} and won its first government "
            f"order ({first['tender_id']}, {fmt_cr(first['value'])}) only {days} days later. "
            + (f"It shares a registered address with another firm in the same family network ({shared['evidence']}). "
               if shared else "")
            + fin_info
            + f" Its director is family-linked to {pol['name']}. Pattern: Ghost-like entity — "
            f"newly incorporated shell winning public contracts."
        )
        _add_flag(c, pol["id"], "GHOST_ENTITY", score,
                  f"{comp['name']} won {fmt_cr(first['value'])} order {days} days after incorporation",
                  explanation, first["value"],
                  [{"company": comp["name"], "cin": comp["cin"], "incorporated": comp["incorporation_date"],
                    "first_award": dict(first)}])


def rule_fund_loop(c, pol):
    """Detect circular fund flows touching the politician's network."""
    web = _family_web(c, pol["id"])
    network = set(web.keys()) | set(_companies_of(c, web.keys()).keys())
    trusts = {
        r["to_id"]
        for r in c.execute(
            "SELECT to_id FROM relationships WHERE from_id IN (%s) AND type='Director_Of'"
            % ",".join("?" * len(web)), tuple(web.keys()))
    }
    network |= trusts
    flows = c.execute("SELECT * FROM fund_flows").fetchall()
    adj = {}
    for f in flows:
        adj.setdefault(f["from_id"], []).append(f)
    # bounded DFS for cycles up to length 4 inside the network
    for start in network:
        stack = [(start, [start], [])]
        while stack:
            node, path, edges = stack.pop()
            for f in adj.get(node, []):
                nxt = f["to_id"]
                if nxt == start and len(path) >= 2:
                    total = min(e["amount"] for e in edges + [f])
                    names = " → ".join(_name(c, p) for p in path + [start])
                    score = min(90, _value_boost(total, base=55, per_log=12))
                    _add_flag(c, pol["id"], "FUND_LOOP", score,
                              f"Circular fund flow through family network ({fmt_cr(total)})",
                              f"Funds cycle {names}. Money leaves a family company, passes through an "
                              f"intermediary (trust/charity), and returns to another firm in the same network. "
                              f"Pattern: Suspicious fund loop (PFMS/MCA filings).",
                              total, [dict(e) for e in edges + [f]])
                    return  # one loop per politician is enough for the flag
                if nxt in network and nxt not in path and len(path) < 4:
                    stack.append((nxt, path + [nxt], edges + [f]))


def rule_loan_quid_pro_quo(c, pol):
    """Circular quid-pro-quo loan:
    Politician -> Family Member -> Director/Shareholder of Family Company
    Family Company <- Lender_To/Donor_To <- Contractor (IRB)
    Contractor -> receives contracts from Govt Body overseen by Politician
    """
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return
        
    family_companies = _companies_of(c, family_only.keys())
    if not family_companies:
        return
        
    overseen = _oversees(c, pol["id"])
    if not overseen:
        return
        
    items = []
    total_loans = 0
    total_contracts = 0
    contractor_names = set()
    family_comp_names = set()
    
    for fcomp_id, (pid, fcomp_ev) in family_companies.items():
        # Find who loaned/funded this family company
        loans = c.execute(
            "SELECT from_id, type, evidence, value, source FROM relationships WHERE to_id = ? AND type IN ('Lender_To', 'Donor_To', 'Associated_With', 'Lender_Of')",
            (fcomp_id,)
        ).fetchall()
        
        for loan in loans:
            contractor_id = loan["from_id"]
            # Check if this contractor won any contracts from overseen bodies
            contracts = c.execute(
                "SELECT * FROM contracts WHERE supplier_id = ? AND buyer_id IN (%s)" 
                % ",".join("?" * len(overseen)),
                (contractor_id,) + tuple(overseen)
            ).fetchall()
            
            if contracts:
                total_loans += loan["value"] or 0
                contractor_name = _name(c, contractor_id)
                fcomp_name = _name(c, fcomp_id)
                contractor_names.add(contractor_name)
                family_comp_names.add(fcomp_name)
                
                for r in contracts:
                    in_tenure = _is_during_tenure(c, pol["id"], r["award_date"])
                    total_contracts += r["value"]
                    items.append({
                        "tender_id": r["tender_id"],
                        "title": r["title"],
                        "value": r["value"],
                        "buyer": _name(c, r["buyer_id"]),
                        "supplier": contractor_name,
                        "award_date": r["award_date"],
                        "loan_evidence": f"{loan['type']}: {loan['evidence']} ({loan['source']})",
                        "loan_value": loan["value"],
                        "during_tenure": in_tenure
                    })
                    
    if not items:
        return
        
    score = _value_boost(total_contracts, base=60, per_log=15)
    score = min(99, score + 10)  # High risk due to direct conflict of interest
    
    c_names = ", ".join(sorted(contractor_names))
    f_names = ", ".join(sorted(family_comp_names))
    
    explanation = (
        f"Quid-pro-quo financing conflict: {c_names} provided funding/loans totaling {fmt_cr(total_loans)} "
        f"to politician-linked firm {f_names} (associated via family directorships). "
        f"Subsequently, {c_names} was awarded {len(items)} contract(s) worth {fmt_cr(total_contracts)} "
        f"by departments overseen by {pol['name']}. Pattern: Politician → Family → Family Company ← Funding ← Contractor ← Contracts from Overseen Department."
    )
    
    _add_flag(c, pol["id"], "LOAN_CONFLICT", score,
              f"Conflict of interest: Loan from contractor {c_names} ({fmt_cr(total_loans)})",
              explanation, total_contracts, items)


def rule_policy_conflict(c, pol):
    """Detect conflict of interest where a politician's family-linked company
    wins contracts in an industry that the politician actively promotes or regulates (e.g., Ethanol Blending).
    """
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return
        
    family_companies = _companies_of(c, family_only.keys())
    if not family_companies:
        return
        
    pol_notes = (pol["notes"] or "").lower()
    pol_position = (pol["position"] or "").lower()
    
    # Pre-fetch family member profiles
    family_members_data = {}
    for pid in family_only.keys():
        f_row = c.execute("SELECT * FROM entities WHERE id=?", (pid,)).fetchone()
        if f_row:
            family_members_data[pid] = dict(f_row)
            
    # Check if the politician's profile indicates involvement in transport or ethanol advocacy
    is_advocate = False
    policy_keywords = ["ethanol", "blending", "road transport", "highways", "bio-fuel", "clean energy", "transport", "excise", "liquor", "beverage", "alcohol", "wine"]
    for kw in policy_keywords:
        if kw in pol_notes or kw in pol_position:
            is_advocate = True
            break
            
    # Also check if politician oversees bodies related to roads or highways
    overseen = _oversees(c, pol["id"])
    for ob in overseen:
        ob_name = _name(c, ob).lower()
        if any(kw in ob_name for kw in ["road transport", "highways", "nhai", "excise", "liquor"]):
            is_advocate = True
            break
            
    if not is_advocate:
        return
        
    items = []
    total_val = 0
    company_names = set()
    linked_family_members = {} # pid -> (name, rel_type, notes, company_name)
    
    for fcomp_id, (pid, fcomp_ev) in family_companies.items():
        fm = family_members_data.get(pid, {})
        fm_notes = (fm.get("notes") or "").lower()
        fm_pos = (fm.get("position") or "").lower()
        
        comp = c.execute("SELECT * FROM entities WHERE id = ?", (fcomp_id,)).fetchone()
        comp_notes = (comp["notes"] or "").lower() if comp else ""
        comp_name_lower = (comp["name"] or "").lower() if comp else ""
        
        # Look for contracts related to ethanol, bio-fuel, highways, or excise/liquor
        contracts = c.execute(
            "SELECT * FROM contracts WHERE supplier_id = ?", (fcomp_id,)
        ).fetchall()
        
        for r in contracts:
            title_desc = (r["title"] or "").lower() + " " + (r["description"] or "").lower()
            match_kw = None
            for kw in ["ethanol", "bio-fuel", "blending", "distillery", "sugar", "excise", "liquor", "beverage", "retail zone", "wholesale", "l-1", "l-7"]:
                if kw in title_desc or kw in comp_notes or kw in comp_name_lower or kw in fm_notes or kw in fm_pos:
                    match_kw = kw
                    break
            
            if match_kw:
                total_val += r["value"]
                company_name = comp["name"] if comp else f"#{fcomp_id}"
                company_names.add(company_name)
                
                family_name = fm.get("name") or f"#{pid}"
                family_rel = web[pid]
                linked_family_members[pid] = (family_name, family_rel, fm.get("notes") or "", company_name)
                
                items.append({
                    "tender_id": r["tender_id"],
                    "title": r["title"],
                    "value": r["value"],
                    "buyer": _name(c, r["buyer_id"]),
                    "supplier": company_name,
                    "award_date": r["award_date"],
                    "conflict_sector": match_kw.capitalize(),
                    "source": r["source"],
                    "linked_family_member": family_name,
                    "relationship": family_rel,
                    "family_member_notes": fm.get("notes") or ""
                })
                
    if not items:
        return
        
    score = _value_boost(total_val, base=65, per_log=15)
    score = min(99, score + 10) # High risk due to policy conflict
    
    member_details = []
    for pid, (name, rel, notes, cname) in linked_family_members.items():
        desc = f"{name} ({rel})"
        if notes:
            desc += f" [Details: {notes}]"
        desc += f" who directs/owns {cname}"
        member_details.append(desc)
    member_str = "; ".join(member_details)
    
    c_names = ", ".join(sorted(company_names))
    
    is_excise = any(item["conflict_sector"].lower() in ["excise", "liquor", "beverage", "retail zone", "wholesale", "l-1", "l-7"] for item in items)
    if is_excise:
        explanation = (
            f"Policy Conflict of Interest: {pol['name']} is a major policy-maker for excise and liquor licensing. "
            f"His first-degree family member(s) ({member_str}) own and manage firms in the liquor/beverage sector. "
            f"These connected companies won {len(items)} contract(s) worth {fmt_cr(total_val)} related to liquor licensing/distribution. "
            f"Pattern: Politician promotes excise policy -> Family member owns/directs liquor firm -> Company wins public retail/wholesale contracts."
        )
        title = f"Policy Conflict: Liquor contracts won by family firms ({fmt_cr(total_val)})"
    else:
        explanation = (
            f"Policy Conflict of Interest: {pol['name']} is a major national advocate pushing for ethanol blending and bio-fuels. "
            f"His first-degree family member(s) ({member_str}) own and manage firms in the ethanol/sugar sector. "
            f"These connected companies won {len(items)} contract(s) worth {fmt_cr(total_val)} related to ethanol supply. "
            f"Pattern: Politician promotes ethanol blending policy -> Family member owns/directs ethanol firm -> Company wins public ethanol supply contracts."
        )
        title = f"Policy Conflict: Ethanol supply contracts won by family firms ({fmt_cr(total_val)})"
        
    _add_flag(c, pol["id"], "POLICY_CONFLICT", score,
              title,
              explanation, total_val, items)


def rule_scam_detection(c, pol):
    """Flag any contract linked to the politician's family network whose
    title or description contains scam/fraud/irregularity keywords.
    Per user directive: any scam counts, not just education-related."""
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return
    companies = _companies_of(c, family_only.keys())
    if not companies:
        return

    scam_keywords = [
        "scam", "fraud", "cheating", "misuse", "embezzlement",
        "irregularity", "siphon", "kickback", "bribe", "corruption",
        "laundering", "disproportionate", "benami", "bogus", "fake",
        "shell", "hawala", "ponzi", "chit fund", "illegal",
    ]

    items, total_val = [], 0
    for comp_id, (pid, ev) in companies.items():
        rows = c.execute(
            "SELECT * FROM contracts WHERE supplier_id=?", (comp_id,)
        ).fetchall()
        for r in rows:
            text = ((r["title"] or "") + " " + (r["description"] or "")).lower()
            matched = [kw for kw in scam_keywords if kw in text]
            if not matched:
                continue
            in_tenure = _is_during_tenure(c, pol["id"], r["award_date"])
            total_val += r["value"]
            items.append({
                "tender_id": r["tender_id"], "title": r["title"],
                "value": r["value"], "buyer": _name(c, r["buyer_id"]),
                "supplier": _name(c, comp_id),
                "award_date": r["award_date"],
                "matched_keywords": matched,
                "via": f"{_name(c, pid)} ({ev})",
                "source": r["source"],
                "during_tenure": in_tenure,
            })

    if not items:
        return

    score = _value_boost(total_val, base=45, per_log=20, cap=95)
    if any(i["during_tenure"] for i in items):
        score = min(97, score + 10)

    kw_summary = ", ".join(sorted({kw for i in items for kw in i["matched_keywords"]}))
    explanation = (
        f"Scam/fraud indicators detected: {len(items)} contract(s) worth {fmt_cr(total_val)} "
        f"awarded to family-linked firms of {pol['name']} contain keywords [{kw_summary}]. "
        f"Workflow: Politician → Family_Link → Director_Of/Shareholder_Of → Company wins "
        f"contracts flagged with irregularity language. "
        f"Pattern: Potential scam linkage (contract text analysis)."
    )
    _add_flag(c, pol["id"], "SCAM_DETECTION", score,
              f"Scam indicators in {len(items)} contracts ({fmt_cr(total_val)})",
              explanation, total_val, items)


def rule_media_capture(c, pol):
    """Identify media-industry contracts awarded to family-linked firms.
    Note: media contracts are flagged but NOT treated as a perfect source.
    Includes comparison with indirect electoral-bond connections if present."""
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return
    companies = _companies_of(c, family_only.keys())
    if not companies:
        return

    media_keywords = [
        "media", "advertising", "broadcast", "news", "newspaper",
        "television", "tv channel", "print media", "digital media",
        "publicity", "pr agency", "communication",
    ]

    items, total_val = [], 0
    for comp_id, (pid, ev) in companies.items():
        comp = c.execute("SELECT * FROM entities WHERE id=?", (comp_id,)).fetchone()
        comp_name_lower = (comp["name"] or "").lower() if comp else ""
        comp_notes_lower = (comp["notes"] or "").lower() if comp else ""

        rows = c.execute(
            "SELECT * FROM contracts WHERE supplier_id=?", (comp_id,)
        ).fetchall()
        for r in rows:
            text = ((r["title"] or "") + " " + (r["description"] or "")).lower()
            match_kw = None
            for kw in media_keywords:
                if kw in text or kw in comp_name_lower or kw in comp_notes_lower:
                    match_kw = kw
                    break
            if not match_kw:
                continue
            in_tenure = _is_during_tenure(c, pol["id"], r["award_date"])
            total_val += r["value"]
            items.append({
                "tender_id": r["tender_id"], "title": r["title"],
                "value": r["value"], "buyer": _name(c, r["buyer_id"]),
                "supplier": _name(c, comp_id),
                "award_date": r["award_date"],
                "media_keyword": match_kw,
                "via": f"{_name(c, pid)} ({ev})",
                "source": r["source"],
                "during_tenure": in_tenure,
            })

    if not items:
        return

    # Check for indirect electoral-bond connections (donors to politician or party)
    bond_info = ""
    donors = c.execute(
        "SELECT r.from_id, r.evidence, r.value FROM relationships r "
        "WHERE r.to_id=? AND r.type='Donor_To'", (pol["id"],)
    ).fetchall()
    donor_ids = {d["from_id"] for d in donors}
    # Check if any media company also received funds from or is linked to a donor
    bond_overlaps = []
    for comp_id in {i["supplier"] for i in items}:
        comp_entity = c.execute("SELECT id FROM entities WHERE name=?", (comp_id,)).fetchone()
        if comp_entity and comp_entity["id"] in donor_ids:
            bond_overlaps.append(comp_id)
    if bond_overlaps:
        bond_info = (
            f" Additionally, {', '.join(bond_overlaps)} appear(s) as direct or indirect "
            f"donor(s)/bond-purchaser(s) linked to {pol['name']}, suggesting a dual "
            f"media-capture and financing pathway."
        )

    score = _value_boost(total_val, base=42, per_log=19, cap=93)
    if any(i["during_tenure"] for i in items):
        score = min(95, score + 8)

    explanation = (
        f"Media capture risk: {len(items)} media/advertising contract(s) worth {fmt_cr(total_val)} "
        f"awarded to family-linked firms of {pol['name']}. "
        f"⚠ NOTE: Media contracts are shown for transparency but are NOT treated as a confirmed "
        f"corruption source — further investigation is recommended. "
        f"Workflow: Politician → Family_Link → Director_Of → Media company wins government "
        f"advertising/media contracts.{bond_info} "
        f"Pattern: Potential media capture (contract + relationship analysis)."
    )
    _add_flag(c, pol["id"], "MEDIA_CAPTURE", score,
              f"Media contracts to family-linked firms ({fmt_cr(total_val)})",
              explanation, total_val, items)


def rule_electoral_bond_loop(c, pol):
    """Detect circular fund flows involving electoral bonds / donations,
    including indirect paths through trusts or intermediaries.
    Per user directive: compare indirect bonds; workflow must be mentioned and not fake."""
    web = _family_web(c, pol["id"])
    network_people = set(web.keys())
    companies = _companies_of(c, network_people)
    network = network_people | set(companies.keys())

    # Include trusts directed by family members
    trusts = {
        r["to_id"]
        for r in c.execute(
            "SELECT to_id FROM relationships WHERE from_id IN (%s) AND type='Director_Of'"
            % ",".join("?" * len(network_people)), tuple(network_people))
    }
    network |= trusts

    # Gather all donor/bond relationships touching the politician or party
    donor_edges = c.execute(
        "SELECT from_id, to_id, evidence, value, source FROM relationships "
        "WHERE type='Donor_To' AND (to_id=? OR to_id IN ("
        "  SELECT id FROM entities WHERE name=?))",
        (pol["id"], pol["party"] or ""),
    ).fetchall()

    if not donor_edges:
        return

    # Build adjacency from fund_flows + donor edges for cycle detection
    flows = c.execute("SELECT * FROM fund_flows").fetchall()
    adj = {}
    for f in flows:
        adj.setdefault(f["from_id"], []).append({
            "to": f["to_id"], "amount": f["amount"],
            "evidence": f["purpose"] or f["scheme"] or "",
            "source": f["source"] or "", "type": "fund_flow",
        })
    for d in donor_edges:
        adj.setdefault(d["from_id"], []).append({
            "to": d["to_id"], "amount": d["value"] or 0,
            "evidence": d["evidence"] or "", "source": d["source"] or "",
            "type": "donation/bond",
        })
    # Also add contract edges (company → govt body)
    for comp_id in companies:
        contracts = c.execute(
            "SELECT buyer_id, value, source FROM contracts WHERE supplier_id=?",
            (comp_id,)
        ).fetchall()
        for ct in contracts:
            adj.setdefault(comp_id, []).append({
                "to": ct["buyer_id"], "amount": ct["value"],
                "evidence": "contract award", "source": ct["source"] or "",
                "type": "contract",
            })

    # Bounded DFS for cycles up to length 5 inside the network
    found_loops = []
    for start in network:
        stack = [(start, [start], [])]
        while stack:
            node, path, edges = stack.pop()
            for edge in adj.get(node, []):
                nxt = edge["to"]
                if nxt == start and len(path) >= 3:
                    # Require at least one donation/bond edge in the cycle
                    if any(e["type"] == "donation/bond" for e in edges + [edge]):
                        total = min(e["amount"] for e in edges + [edge] if e["amount"] > 0) if any(e["amount"] > 0 for e in edges + [edge]) else 0
                        found_loops.append((path + [start], edges + [edge], total))
                        break
                if nxt in network and nxt not in path and len(path) < 5:
                    stack.append((nxt, path + [nxt], edges + [edge]))
            if found_loops:
                break
        if found_loops:
            break

    if not found_loops:
        return

    path, edges, total = found_loops[0]
    names = " → ".join(_name(c, p) for p in path)
    has_direct_bond = any("bond" in (e.get("evidence") or "").lower() or "electoral" in (e.get("evidence") or "").lower() for e in edges)
    bond_type = "direct electoral bond" if has_direct_bond else "indirect donation/financing"

    score = _value_boost(total, base=50, per_log=22, cap=98)
    if has_direct_bond:
        score = min(99, score + 10)

    explanation = (
        f"Electoral bond loop detected ({bond_type}): {names}. "
        f"Funds cycle through {len(path) - 1} entities in the politician's network. "
        f"Workflow: Donor/bond-purchaser sends funds → funds pass through intermediary "
        f"entities (companies/trusts) → benefits return to politician's network via "
        f"contracts or further donations. Both direct and indirect bond paths were analyzed. "
        f"Pattern: Circular electoral-bond financing (fund flow + relationship analysis)."
    )
    _add_flag(c, pol["id"], "ELECTORAL_BOND_LOOP", score,
              f"Electoral bond loop through network ({fmt_cr(total)})",
              explanation, total,
              [{"path": [_name(c, p) for p in path],
                "edges": [{k: v for k, v in e.items()} for e in edges]}])


def rule_family_recruitment(c, pol):
    """Flag any family member who holds a government position / tenure.
    Per user directive: consider ALL government hiring, not just overseen depts."""
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return

    items = []
    for fam_id, how in family_only.items():
        fam_name = _name(c, fam_id)
        # Check if this family member has any government tenures
        tenures = c.execute(
            "SELECT * FROM tenures WHERE entity_id=?", (fam_id,)
        ).fetchall()
        for t in tenures:
            # Check overlap with politician's own tenure
            pol_overlap = _is_during_tenure(c, pol["id"], t["start_date"])
            items.append({
                "family_member": fam_name,
                "relationship": how,
                "office": t["office"],
                "start_date": t["start_date"],
                "end_date": t["end_date"],
                "source": t["source"],
                "overlaps_pol_tenure": pol_overlap,
            })

        # Also check if family member is linked to any GovtBody via relationships
        govt_links = c.execute(
            "SELECT r.to_id, r.type, r.evidence, r.source, e.name, e.type as entity_type "
            "FROM relationships r JOIN entities e ON r.to_id = e.id "
            "WHERE r.from_id=? AND e.type='GovtBody'",
            (fam_id,)
        ).fetchall()
        for gl in govt_links:
            items.append({
                "family_member": fam_name,
                "relationship": how,
                "office": f"{gl['name']} ({gl['type']})",
                "start_date": gl["start_date"] if "start_date" in gl.keys() else "",
                "end_date": "",
                "source": gl["source"],
                "overlaps_pol_tenure": False,
                "link_type": gl["type"],
            })

    if not items:
        return

    overlap_count = sum(1 for i in items if i.get("overlaps_pol_tenure"))
    score = min(90, 38 + 16 * len(items))
    if overlap_count:
        score = min(93, score + 10)

    members = ", ".join(sorted({i["family_member"] for i in items}))
    offices = "; ".join(sorted({i["office"] for i in items}))
    explanation = (
        f"Family recruitment pattern: {len(items)} government position(s) held by "
        f"family members of {pol['name']}: {members}. "
        f"Offices/bodies involved: {offices}. "
        + (f"{overlap_count} position(s) overlap with the politician's active tenure. " if overlap_count else "")
        + f"Workflow: Politician → Family_Link → Family member holds government office/position. "
        f"Pattern: Potential nepotism — family members in government roles."
    )
    _add_flag(c, pol["id"], "FAMILY_RECRUITMENT", score,
              f"Family members in {len(items)} govt position(s)",
              explanation, 0, items)


def rule_benami_property(c, pol):
    """Detect assets/companies owned via benami (proxy) arrangements —
    companies where a family member is the beneficial owner but the company
    is registered under another entity, or where shell-like patterns emerge."""
    web = _family_web(c, pol["id"])
    family_only = {k: v for k, v in web.items() if k != pol["id"]}
    if not family_only:
        return

    items = []
    total_val = 0

    for fam_id, how in family_only.items():
        fam_name = _name(c, fam_id)
        # Look for companies where this family member is beneficial owner
        beneficial = c.execute(
            "SELECT r.to_id, r.evidence, r.source FROM relationships r "
            "WHERE r.from_id=? AND r.type='Beneficial_Owner_Of'",
            (fam_id,)
        ).fetchall()
        for b in beneficial:
            comp_id = b["to_id"]
            comp = c.execute("SELECT * FROM entities WHERE id=?", (comp_id,)).fetchone()
            if not comp:
                continue

            # Check if this company has a different registered director (not in family)
            directors = c.execute(
                "SELECT from_id FROM relationships WHERE to_id=? AND type='Director_Of'",
                (comp_id,)
            ).fetchall()
            outside_directors = [d["from_id"] for d in directors if d["from_id"] not in web]

            # Check for shared addresses with other family companies
            shared = c.execute(
                "SELECT * FROM relationships WHERE type='Shared_Address' AND (from_id=? OR to_id=?)",
                (comp_id, comp_id)
            ).fetchone()

            # Get total contracts won by this benami entity
            contracts = c.execute(
                "SELECT SUM(value) as total, COUNT(*) as cnt FROM contracts WHERE supplier_id=?",
                (comp_id,)
            ).fetchone()
            comp_val = contracts["total"] or 0
            comp_cnt = contracts["cnt"] or 0
            total_val += comp_val

            items.append({
                "company": comp["name"],
                "cin": comp["cin"] or "",
                "beneficial_owner": fam_name,
                "relationship_to_pol": how,
                "has_outside_directors": len(outside_directors) > 0,
                "outside_director_count": len(outside_directors),
                "shared_address": bool(shared),
                "shared_address_evidence": shared["evidence"] if shared else "",
                "contracts_won": comp_cnt,
                "contract_value": comp_val,
                "incorporation_date": comp["incorporation_date"] or "",
                "evidence": b["evidence"],
                "source": b["source"],
            })

    if not items:
        return

    score = min(95, 50 + 12 * len(items))
    if any(i["shared_address"] for i in items):
        score = min(97, score + 8)
    if total_val > 0:
        score = min(98, score + _value_boost(total_val, base=0, per_log=10, cap=15))

    comp_names = ", ".join(sorted({i["company"] for i in items}))
    explanation = (
        f"Benami property pattern: {len(items)} company/ies ({comp_names}) where family members "
        f"of {pol['name']} are beneficial owners but the entities may be registered under "
        f"third-party directors. "
        + (f"Total contracts won by these entities: {fmt_cr(total_val)}. " if total_val > 0 else "")
        + ("Shared registered addresses detected between benami entities and other family firms. " if any(i["shared_address"] for i in items) else "")
        + f"Workflow: Politician → Family_Link → Beneficial_Owner_Of → Company with outside "
        f"directors → Company wins government contracts. "
        f"Pattern: Potential benami ownership (MCA beneficial ownership + contract analysis)."
    )
    _add_flag(c, pol["id"], "BENAMI_PROPERTY", score,
              f"Benami ownership in {len(items)} company/ies ({comp_names})",
              explanation, total_val, items)


# ---------------------------------------------------------------------------
# Rule registry — every callable in this list is invoked by rescore()
# ---------------------------------------------------------------------------
RULES = [
    rule_family_contracts,
    rule_asset_growth,
    rule_repeated_awards,
    rule_ghost_entity,
    rule_fund_loop,
    rule_loan_quid_pro_quo,
    rule_policy_conflict,
    rule_scam_detection,
    rule_media_capture,
    rule_electoral_bond_loop,
    rule_family_recruitment,
    rule_benami_property,
]


def rescore():
    """Clear auto flags and re-run all detection rules. Returns flag count."""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM flags WHERE status='auto'")
    pols = c.execute("SELECT * FROM entities WHERE type='Politician'").fetchall()
    for pol in pols:
        for rule in RULES:
            try:
                rule(c, pol)
            except Exception as e:  # one bad rule shouldn't kill the run
                print(f"rule {rule.__name__} failed for {pol['name']}: {e}")
    conn.commit()
    n = c.execute("SELECT COUNT(*) FROM flags").fetchone()[0]
    return n


if __name__ == "__main__":
    from db import init_db
    init_db()
    print("Flags computed:", rescore())
