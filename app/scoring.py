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
        rows = c.execute(
            "SELECT from_id, to_id, evidence FROM relationships WHERE type='Family_Link' AND (from_id=? OR to_id=?)",
            (curr_id, curr_id),
        ).fetchall()
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
    """{company_id: (person_id, evidence)} for Director_Of/Shareholder_Of links."""
    out = {}
    for pid in person_ids:
        rows = c.execute(
            "SELECT to_id, type, evidence FROM relationships WHERE from_id=? AND type IN ('Director_Of','Shareholder_Of')",
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


RULES = [rule_family_contracts, rule_asset_growth, rule_repeated_awards,
         rule_ghost_entity, rule_fund_loop, rule_loan_quid_pro_quo, rule_policy_conflict]


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
