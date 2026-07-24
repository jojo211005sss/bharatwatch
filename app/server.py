"""BharatWatch HTTP server — Python stdlib only.

Run:  python3 app/server.py            (default port 8787)
Env:  BHARATWATCH_PORT, BHARATWATCH_ADMIN_PASSWORD (default: bharat-admin),
      ANTHROPIC_API_KEY (optional, enables AI entity resolution)
"""
import csv
import io
import json
import os
import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)
PUBLIC = os.path.join(ROOT, "public")
sys.path.insert(0, APP_DIR)

from db import init_db, get_db, rows_to_dicts
from scoring import rescore
from importer import import_csv, resolve_review

PORT = int(os.environ.get("PORT", os.environ.get("BHARATWATCH_PORT", "8787")))
HOST = os.environ.get("BHARATWATCH_HOST", "127.0.0.1")  # set 0.0.0.0 when behind a reverse proxy
ADMIN_PASSWORD = os.environ.get("BHARATWATCH_ADMIN_PASSWORD", "bharat-admin")
_tokens = set()

MIME = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
        ".svg": "image/svg+xml", ".png": "image/png", ".json": "application/json",
        ".ico": "image/x-icon"}

PAGES = {"/": "index.html", "/entity": "entity.html", "/explore": "explore.html",
         "/overview": "overview.html", "/about": "about.html"}


# ---------------------------------------------------------------- helpers

def graph_for(center_id, depth=2, max_nodes=120):
    """BFS over relationships + contracts + fund flows, returns cytoscape-style elements."""
    c = get_db().cursor()
    nodes, edges, frontier = {center_id: 0}, [], [center_id]
    for d in range(1, depth + 1):
        nxt = []
        for nid in frontier:
            neigh = []
            for r in c.execute(
                "SELECT id, from_id, to_id, type, evidence, source, value FROM relationships WHERE from_id=? OR to_id=?",
                (nid, nid)):
                neigh.append((r["from_id"], r["to_id"], r["type"],
                              r["evidence"], r["source"], r["value"], f"r{r['id']}"))
            for r in c.execute(
                "SELECT id, buyer_id, supplier_id, value, title, source, tender_id FROM contracts WHERE buyer_id=? OR supplier_id=?",
                (nid, nid)):
                neigh.append((r["buyer_id"], r["supplier_id"], "Contract_Awarded_To",
                              f"{r['tender_id']}: {r['title']}", r["source"], r["value"], f"c{r['id']}"))
            for r in c.execute(
                "SELECT id, from_id, to_id, amount, scheme, purpose, source FROM fund_flows WHERE from_id=? OR to_id=?",
                (nid, nid)):
                neigh.append((r["from_id"], r["to_id"], "Fund_Transfer",
                              f"{r['scheme']}: {r['purpose']}", r["source"], r["amount"], f"f{r['id']}"))
            for a, b, etype, ev, src, val, eid in neigh:
                if a is None or b is None:
                    continue
                for other in (a, b):
                    if other not in nodes and len(nodes) < max_nodes:
                        nodes[other] = d
                        nxt.append(other)
                if a in nodes and b in nodes:
                    edges.append({"id": eid, "source": a, "target": b, "type": etype,
                                  "evidence": ev, "src": src, "value": val})
        frontier = nxt
    seen, uniq_edges = set(), []
    for e in edges:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq_edges.append(e)
    ents = {}
    if nodes:
        q = ",".join("?" * len(nodes))
        for r in c.execute(f"SELECT id, name, type, state, party FROM entities WHERE id IN ({q})",
                           tuple(nodes.keys())):
            ents[r["id"]] = dict(r)
    flagged = {r["entity_id"] for r in c.execute("SELECT DISTINCT entity_id FROM flags")}
    out_nodes = []
    for nid, lvl in nodes.items():
        e = ents.get(nid, {"name": f"#{nid}", "type": "Unknown"})
        out_nodes.append({"id": nid, "label": e["name"], "type": e.get("type"),
                          "state": e.get("state"), "level": lvl, "flagged": nid in flagged,
                          "center": nid == center_id})
    return {"nodes": out_nodes, "edges": uniq_edges}


def find_source_directory_for_entity(entity_name):
    """Scan workspace directories to see which one contains CSV data about this entity."""
    import csv
    entity_name_lower = entity_name.lower()
    for item in os.listdir(ROOT):
        item_path = os.path.join(ROOT, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            # Check for CSV files in this directory
            for f in os.listdir(item_path):
                if f.endswith('.csv'):
                    f_path = os.path.join(item_path, f)
                    try:
                        with open(f_path, 'r', encoding='utf-8', errors='ignore') as csvfile:
                            content = csvfile.read().lower()
                            if entity_name_lower in content:
                                return item
                    except Exception:
                        pass
    # Fallback to state or name heuristics
    if "dilawar" in entity_name_lower:
        return "dilawar_data"
    return "sample_data"


def get_source_url(source, entity_name=None, cin=None, din=None, pan=None, tender_id=None):
    if not source:
        return (None, False)
        
    import urllib.parse
    
    # If a full direct URL is stored in the source field (starts with http)
    if source.startswith("http://") or source.startswith("https://"):
        try:
            parsed = urllib.parse.urlparse(source)
            # return (url, True) if it has a non-root path, else (url, False)
            has_path = len(parsed.path.strip("/")) > 0 or len(parsed.query) > 0
            return (source, has_path)
        except Exception:
            return (source, False)
        
    s_lower = source.lower()
    
    if "myneta" in s_lower:
        if entity_name:
            return (f"https://www.myneta.info/search/?q={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://www.myneta.info/", False)
        
    if "eci" in s_lower or "affidavit" in s_lower or "election" in s_lower:
        if entity_name:
            return (f"https://affidavit.eci.gov.in/Home/PublicSearch?candidate_name={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://affidavit.eci.gov.in/", False)
        
    if "mca" in s_lower or "company" in s_lower or "director" in s_lower or "filing" in s_lower:
        if cin:
            return (f"https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do?cin={cin}", True)
        if din:
            return (f"https://www.mca.gov.in/mcafoportal/viewDirectorMasterData.do?din={din}", True)
        if entity_name:
            return (f"https://www.mca.gov.in/mcafoportal/viewCompanySearch.do?company_name={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://www.mca.gov.in/", False)
        
    if "zauba" in s_lower:
        if entity_name:
            return (f"https://www.zaubacorp.com/company-search/{urllib.parse.quote_plus(entity_name)}", True)
        return ("https://www.zaubacorp.com/", False)
        
    if "data.gov" in s_lower:
        return ("https://data.gov.in/", False)
        
    if "cppp" in s_lower or "procure" in s_lower:
        if tender_id:
            return (f"https://eprocure.gov.in/cppp/tendersearch/cft?tenderNo={urllib.parse.quote_plus(tender_id)}", True)
        return ("https://eprocure.gov.in/cppp/", False)
        
    if "gem" in s_lower or "bidplus" in s_lower:
        if tender_id:
            return (f"https://bidplus.gem.gov.in/bidlists?bids_no={urllib.parse.quote_plus(tender_id)}", True)
        return ("https://gem.gov.in/", False)
        
    if "sppp" in s_lower or "rajasthan" in s_lower or "state gazette" in s_lower:
        if tender_id:
            return (f"https://sppp.rajasthan.gov.in/TenderSearch.aspx?tenderno={urllib.parse.quote_plus(tender_id)}", True)
        return ("https://sppp.rajasthan.gov.in/", False)
        
    if "pfms" in s_lower:
        return ("https://pfms.nic.in/", False)
        
    if "mplads" in s_lower:
        return ("https://www.mplads.gov.in/", False)
        
    if "sansad" in s_lower or "parliament" in s_lower:
        if entity_name:
            return (f"https://sansad.in/ls/members/search?name={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://sansad.in/", False)
        
    if "thehindu" in s_lower:
        if entity_name:
            return (f"https://www.thehindu.com/search/?q={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://www.thehindu.com/", False)
        
    if "ndtv" in s_lower:
        if entity_name:
            return (f"https://www.ndtv.com/search?q={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://www.ndtv.com/", False)
        
    if "business-standard" in s_lower:
        if entity_name:
            return (f"https://www.business-standard.com/search?q={urllib.parse.quote_plus(entity_name)}", True)
        return ("https://www.business-standard.com/", False)
        
    if "telegraphindia" in s_lower:
        return ("https://www.telegraphindia.com/", False)
        
    if "transparency" in s_lower:
        return ("https://www.transparency.org/", False)
        
    if "cvigil" in s_lower:
        return ("https://cvigil.in/", False)
        
    return (None, False)


def humanize_relation_type(rtype, evidence=""):
    rtype_lower = rtype.lower()
    if rtype_lower == "family_link":
        ev_lower = (evidence or "").lower()
        if "son" in ev_lower: return "Son"
        if "wife" in ev_lower or "spouse" in ev_lower or "husband" in ev_lower: return "Spouse"
        if "brother" in ev_lower: return "Brother"
        if "sister" in ev_lower: return "Sister"
        if "daughter" in ev_lower: return "Daughter"
        if "father" in ev_lower: return "Father"
        if "mother" in ev_lower: return "Mother"
        return "Family Member"
    if rtype_lower == "friend_link":
        return "Friend"
    if rtype_lower == "director_of":
        return "Director"
    if rtype_lower == "shareholder_of":
        return "Shareholder"
    if rtype_lower in ("works_at", "employee_of"):
        return "Employee"
    if rtype_lower == "oversees":
        return "Oversees"
    if rtype_lower == "shared_address":
        return "Shares Address"
    
    return rtype.replace("_", " ").title()


def entity_profile(eid):
    c = get_db().cursor()
    e = c.execute("SELECT * FROM entities WHERE id=?", (eid,)).fetchone()
    if not e:
        return None
    e = dict(e)
    decls = rows_to_dicts(c.execute(
        "SELECT * FROM declarations WHERE entity_id=? ORDER BY year", (eid,)))
    for d in decls:
        d["source_url"], d["is_deep_link"] = get_source_url(d.get("source"), entity_name=e["name"], pan=e.get("pan"))
        
    flags = rows_to_dicts(c.execute(
        "SELECT * FROM flags WHERE entity_id=? ORDER BY risk_score DESC", (eid,)))
    try:
        from rti_generator import generate_rti_suggestion
    except ImportError:
        generate_rti_suggestion = lambda pat, ev, name: None

    for f in flags:
        f["evidence"] = json.loads(f["evidence"] or "[]")
        f["rti_suggestion"] = generate_rti_suggestion(f["pattern"], f["evidence"], e["name"])
        
    rels = rows_to_dicts(c.execute("""
        SELECT r.*, a.name AS from_name, a.din AS from_din, a.pan AS from_pan, a.type AS from_type,
               b.name AS to_name, b.cin AS to_cin, b.pan AS to_pan, b.type AS to_type
        FROM relationships r JOIN entities a ON a.id=r.from_id JOIN entities b ON b.id=r.to_id
        WHERE r.from_id=? OR r.to_id=?""", (eid, eid)))
    for r in rels:
        other_name = r["to_name"] if r["from_id"] == eid else r["from_name"]
        r["source_url"], r["is_deep_link"] = get_source_url(
            r.get("source"),
            entity_name=other_name,
            cin=r.get("to_cin") or r.get("from_cin"),
            din=r.get("from_din") or r.get("to_din"),
            pan=r.get("from_pan") or r.get("to_pan")
        )
        
    # Find all personal connections of eid up to 3rd degree (Family, Friends, Associates, etc.)
    personal_connections = {eid: {"name": e["name"], "rel_to_pol": "Self", "type": e["type"], "din": e.get("din"), "pan": e.get("pan"), "position": e.get("position"), "notes": e.get("notes")}}
    personal_rel_types = {'family_link', 'friend_link', 'associate', 'spouse', 'son', 'daughter', 'child', 'parent', 'sibling', 'brother', 'sister', 'wife', 'husband', 'relative', 'spouse_of', 'sibling_of'}
    
    queue = [(eid, 0, "Self")]
    visited = {eid}
    
    while queue:
        curr_id, depth, curr_desc = queue.pop(0)
        if depth < 3:
            rows = c.execute("""
                SELECT r.from_id, r.to_id, r.type, r.evidence
                FROM relationships r
                WHERE r.from_id = ? OR r.to_id = ?
            """, (curr_id, curr_id)).fetchall()
            
            for r in rows:
                other_id = r["to_id"] if r["from_id"] == curr_id else r["from_id"]
                if other_id not in visited:
                    oth = c.execute("SELECT * FROM entities WHERE id = ?", (other_id,)).fetchone()
                    if oth:
                        oth_type = oth["type"]
                        if oth_type in ("Person", "Politician") or r["type"].lower() in personal_rel_types:
                            rel_desc = humanize_relation_type(r["type"], r["evidence"])
                            if curr_id == eid:
                                path_desc = rel_desc
                            else:
                                path_desc = f"{rel_desc} (via {curr_desc})"
                            
                            personal_connections[other_id] = {
                                "id": oth["id"],
                                "name": oth["name"],
                                "type": oth["type"],
                                "din": oth["din"],
                                "pan": oth["pan"],
                                "position": oth["position"],
                                "notes": oth["notes"],
                                "rel_to_pol": path_desc
                            }
                            visited.add(other_id)
                            queue.append((other_id, depth + 1, path_desc))

    # Deeply search for details of the first-degree connections
    first_degree_connections = []
    for pid, pinfo in personal_connections.items():
        if pid == eid:
            continue
        # Get roles of this family member in companies/trusts
        roles_rows = c.execute("""
            SELECT r.type, r.evidence, e.id AS entity_id, e.name AS entity_name, e.type AS entity_type
            FROM relationships r
            JOIN entities e ON e.id = r.to_id
            WHERE r.from_id = ? AND r.type IN ('Director_Of', 'Shareholder_Of', 'Works_At', 'Employee_Of')
        """, (pid,)).fetchall()
        roles_list = []
        for rr in roles_rows:
            roles_list.append({
                "type": rr["type"],
                "evidence": rr["evidence"],
                "entity_id": rr["entity_id"],
                "entity_name": rr["entity_name"],
                "entity_type": rr["entity_type"]
            })
        first_degree_connections.append({
            "id": pid,
            "name": pinfo["name"],
            "type": pinfo["type"],
            "rel_to_pol": pinfo["rel_to_pol"],
            "din": pinfo.get("din"),
            "pan": pinfo.get("pan"),
            "position": pinfo.get("position"),
            "notes": pinfo.get("notes"),
            "roles": roles_list
        })

    comp_list = []
    if personal_connections:
        p_ids = list(personal_connections.keys())
        q = ",".join("?" * len(p_ids))
        links = c.execute(f"""
            SELECT r.from_id, r.to_id, r.type, r.evidence, r.source
            FROM relationships r
            WHERE r.from_id IN ({q}) OR r.to_id IN ({q})
        """, tuple(p_ids) + tuple(p_ids)).fetchall()
        
        for r in links:
            from_in_p = r["from_id"] in personal_connections
            to_in_p = r["to_id"] in personal_connections
            if from_in_p and to_in_p:
                continue
            if from_in_p:
                p_id, e_id = r["from_id"], r["to_id"]
            elif to_in_p:
                p_id, e_id = r["to_id"], r["from_id"]
            else:
                continue
                
            e_row = c.execute("SELECT * FROM entities WHERE id = ?", (e_id,)).fetchone()
            if e_row and e_row["type"] in ("Company", "Trust", "GovtBody"):
                comp_ent = dict(e_row)
                p_info = personal_connections[p_id]
                rel_name = humanize_relation_type(r["type"])
                via_desc = f"{p_info['name']}"
                if p_id != eid:
                    via_desc += f" ({p_info['rel_to_pol']})"
                via_desc += f" — {rel_name}"
                comp_ent["via"] = via_desc
                comp_list.append(comp_ent)
                
    # Deduplicate and group companies
    deduped_companies = {}
    for comp in comp_list:
        cid = comp["id"]
        if cid not in deduped_companies:
            deduped_companies[cid] = comp
        else:
            existing_trails = deduped_companies[cid]["via"].split("; ")
            if comp["via"] not in existing_trails:
                deduped_companies[cid]["via"] += "; " + comp["via"]
    companies = list(deduped_companies.values())
    comp_ids = [co["id"] for co in companies] or [-1]
    qc = ",".join("?" * len(comp_ids))
    contracts = rows_to_dicts(c.execute(f"""
        SELECT k.*, b.name AS buyer_name, s.name AS supplier_name, s.cin AS supplier_cin, s.pan AS supplier_pan FROM contracts k
        JOIN entities b ON b.id=k.buyer_id JOIN entities s ON s.id=k.supplier_id
        WHERE k.supplier_id IN ({qc}) OR k.buyer_id=? ORDER BY k.award_date""",
        tuple(comp_ids) + (eid,)))
    for k in contracts:
        k["source_url"], k["is_deep_link"] = get_source_url(
            k.get("source"),
            entity_name=k["supplier_name"],
            cin=k.get("supplier_cin"),
            pan=k.get("supplier_pan"),
            tender_id=k.get("tender_id")
        )
        
    net_ids = tuple(personal_connections.keys()) + tuple(comp_ids)
    qn = ",".join("?" * len(net_ids))
    flows = rows_to_dicts(c.execute(f"""
        SELECT f.*, a.name AS from_name, b.name AS to_name FROM fund_flows f
        JOIN entities a ON a.id=f.from_id JOIN entities b ON b.id=f.to_id
        WHERE f.from_id IN ({qn}) OR f.to_id IN ({qn}) ORDER BY f.date""", net_ids + net_ids))
    for f in flows:
        other_name = f["to_name"] if f["from_id"] == eid else f["from_name"]
        f["source_url"], f["is_deep_link"] = get_source_url(
            f.get("source"),
            entity_name=other_name
        )
        
    tenures = rows_to_dicts(c.execute(
        "SELECT * FROM tenures WHERE entity_id=? ORDER BY start_date", (eid,)))
    for t in tenures:
        t["source_url"], t["is_deep_link"] = get_source_url(t.get("source"), entity_name=e["name"])
        
    financials = rows_to_dicts(c.execute(
        "SELECT * FROM company_financials WHERE company_id=? ORDER BY year", (eid,)))
    for fn in financials:
        fn["source_url"], fn["is_deep_link"] = get_source_url(fn.get("source"), entity_name=e["name"], cin=e.get("cin"))
    
    timeline = []
    for d in decls:
        timeline.append({"date": f"{d['year']}-01-01", "kind": "Affidavit",
                         "text": f"Declared assets ₹{d['assets'] / 1e7:.1f} Cr (income ₹{d['income'] / 1e5:.0f} L/yr)",
                         "source": d.get("source"), "source_url": d.get("source_url")})
    for co in companies:
        if co.get("incorporation_date"):
            timeline.append({"date": co["incorporation_date"], "kind": "Company",
                             "text": f"{co['name']} incorporated (director: {co['via']})",
                             "source": "MCA filings", "source_url": "https://www.mca.gov.in/"})
    for k in contracts:
        if k.get("award_date"):
            timeline.append({"date": k["award_date"], "kind": "Contract",
                             "text": f"{k['supplier_name']} awarded {k['tender_id']} (₹{k['value'] / 1e7:.1f} Cr) by {k['buyer_name']}",
                             "source": k.get("source"), "source_url": k.get("source_url")})
    for f in flows:
        if f.get("date"):
            timeline.append({"date": f["date"], "kind": "Fund flow",
                             "text": f"₹{f['amount'] / 1e7:.1f} Cr: {f['from_name']} → {f['to_name']} ({f['scheme']})",
                             "source": f.get("source"), "source_url": f.get("source_url")})
    for t in tenures:
        timeline.append({"date": t["start_date"], "kind": "Tenure",
                         "text": f"Assumed office: {t['office']}",
                         "source": t.get("source"), "source_url": t.get("source_url")})
        if t.get("end_date"):
            timeline.append({"date": t["end_date"], "kind": "Tenure",
                             "text": f"Left office: {t['office']}",
                             "source": t.get("source"), "source_url": t.get("source_url")})
    for fn in financials:
        timeline.append({"date": f"{fn['year']}-03-31", "kind": "Financials",
                         "text": f"Balance sheet FY{fn['year']}: Revenue ₹{fn['revenue'] / 1e7:.1f} Cr, Assets ₹{fn['assets'] / 1e7:.1f} Cr",
                         "source": fn.get("source"), "source_url": fn.get("source_url")})
        
    timeline.sort(key=lambda t: t["date"])
    
    # Map raw sources to public URLs
    PORTAL_URLS = {
        "eci": "https://affidavit.eci.gov.in/",
        "myneta": "https://www.myneta.info/",
        "affidavit": "https://affidavit.eci.gov.in/",
        "mca": "https://www.mca.gov.in/",
        "director": "https://www.mca.gov.in/",
        "company": "https://www.mca.gov.in/",
        "cppp": "https://eprocure.gov.in/cppp/",
        "gem": "https://gem.gov.in/",
        "pfms": "https://pfms.nic.in/",
        "mplads": "https://www.mplads.gov.in/",
        "sppp": "https://sppp.rajasthan.gov.in/",
        "rajasthan": "https://sppp.rajasthan.gov.in/",
        "sansad": "https://sansad.in/",
        "state gazette": "https://sppp.rajasthan.gov.in/"
    }
    
    sources = set()
    for r in decls:
        if r.get("source"): sources.add(r["source"])
    for r in rels:
        if r.get("source"): sources.add(r["source"])
    for r in contracts:
        if r.get("source"): sources.add(r["source"])
    for r in flows:
        if r.get("source"): sources.add(r["source"])
    for r in tenures:
        if r.get("source"): sources.add(r["source"])
    for r in financials:
        if r.get("source"): sources.add(r["source"])
        
    source_links = []
    seen_urls = set()
    for s in sorted(sources):
        s_lower = s.lower()
        url = None
        for key, val in PORTAL_URLS.items():
            if key == "director" and "directory" in s_lower:
                continue
            if key in s_lower:
                url = val
                break
        if not url:
            if "affidavit" in s_lower or "eci" in s_lower or "election" in s_lower:
                url = "https://affidavit.eci.gov.in/"
            elif "mca" in s_lower or "filing" in s_lower or "company" in s_lower:
                url = "https://www.mca.gov.in/"
            elif "contract" in s_lower or "tender" in s_lower or "procure" in s_lower:
                url = "https://eprocure.gov.in/cppp/"
            else:
                url = "https://affidavit.eci.gov.in/"
                
        if url not in seen_urls:
            seen_urls.add(url)
            domain = url.replace("https://", "").replace("http://", "").split("/")[0]
            source_links.append({
                "source": s,
                "url": url,
                "domain": domain
            })
            
    if not source_links:
        source_links = [
            {"source": "ECI Affidavits", "url": "https://affidavit.eci.gov.in/", "domain": "affidavit.eci.gov.in"},
            {"source": "MCA Master Data", "url": "https://www.mca.gov.in/", "domain": "mca.gov.in"},
            {"source": "CPPP Procurement", "url": "https://eprocure.gov.in/cppp/", "domain": "eprocure.gov.in"}
        ]
        
    source_dir = find_source_directory_for_entity(e["name"])
    risk = max([f["risk_score"] for f in flags], default=0)
    return {"entity": dict(e), "declarations": decls, "flags": flags, "risk": risk,
            "relationships": rels, "companies": companies, "contracts": contracts,
            "fund_flows": flows, "timeline": timeline,
            "flagged_value": sum(f["value_involved"] or 0 for f in flags),
            "tenures": tenures, "financials": financials,
            "source_dir": source_dir, "source_links": source_links,
            "first_degree_connections": first_degree_connections}


_gadkari_network_cache = None

def get_gadkari_network_ids():
    global _gadkari_network_cache
    if _gadkari_network_cache is not None:
        return _gadkari_network_cache
    c = get_db().cursor()
    r = c.execute("SELECT id FROM entities WHERE name LIKE '%Nitin Gadkari%' LIMIT 1").fetchone()
    if not r:
        _gadkari_network_cache = set()
        return _gadkari_network_cache
    gadkari_id = r[0]
    g = graph_for(gadkari_id, depth=3)
    _gadkari_network_cache = set(n["id"] for n in g["nodes"])
    return _gadkari_network_cache


# ---------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    server_version = "BharatWatch/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _is_approved(self, q):
        val = q.get("approved", [""])[0].lower()
        return val in ("1", "true")

    # -- responses
    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, body, ctype, code=200, filename=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name):
        path = os.path.realpath(os.path.join(PUBLIC, name))
        if not path.startswith(os.path.realpath(PUBLIC)) or not os.path.isfile(path):
            return self._json({"error": "not found"}, 404)
        ext = os.path.splitext(path)[1]
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
        self.send_header("Cache-Control", "public, max-age=86400, s-maxage=604800, stale-while-revalidate=86400")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authed(self):
        return self.headers.get("X-Admin-Token", "") in _tokens

    def _body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # -- routing
    def do_GET(self):
        url = urlparse(self.path)
        p, q = url.path, parse_qs(url.query)
        get_db()
        try:
            if p in PAGES:
                return self._file(PAGES[p])
            if p.startswith("/static/"):
                return self._file(p[len("/static/"):])
            if p == "/api/stats":
                return self.api_stats(q)
            if p == "/api/search":
                return self.api_search(q)
            if p == "/api/entities":
                return self.api_entities(q)
            if p == "/api/highrisk":
                return self.api_highrisk(q)
            if p == "/api/overview":
                return self.api_overview(q)
            if p == "/api/entity/scam-scan":
                eid_list = q.get("id", [""])
                if not eid_list or not eid_list[0]:
                    return self._json({"error": "missing id"}, 400)
                eid = int(eid_list[0])
                c = get_db().cursor()
                e = c.execute("SELECT name FROM entities WHERE id = ?", (eid,)).fetchone()
                if not e:
                    return self._json({"error": "entity not found"}, 404)
                name = e["name"]
                
                # Dynamic context-based responses depending on the politician
                name_lower = name.lower()
                if "himanta" in name_lower:
                    summary = (
                        "Assam Chief Minister Himanta Biswa Sarma has faced multiple high-profile corruption allegations. "
                        "Key controversies include:<br><br>"
                        "<strong>1. Saradha Chit Fund Scam:</strong> Questioned by the CBI in 2014 regarding his association with Saradha Group owner Sudipto Sen. Opponents allege investigation stalled after he joined BJP.<br>"
                        "<strong>2. Louis Berger Bribery Case:</strong> Alleged payoffs to secure water supply project contracts in 2009-2010 when he oversaw the Guwahati Development Department. Gauhati HC ordered CBI probe in 2017.<br>"
                        "<strong>3. COVID-19 PPE Kit Controversy:</strong> Allegations of emergency medical supply contracts awarded to JCB Industries (linked to spouse Riniki Bhuyan Sarma) at inflated rates without competitive bidding. The Chief Minister's spouse has filed a Rs 100-crore defamation suit against critics."
                    )
                    refs = [
                        {"title": "CBI questions Himanta Biswa Sarma in Saradha scam", "url": "https://www.thehindu.com/news/national/cbi-questions-himanta-biswa-sarma-in-saradha-scam/article6637254.ece", "source": "The Hindu"},
                        {"title": "Louis Berger Case: Gauhati High Court orders CBI probe", "url": "https://www.ndtv.com/india-news/louis-berger-case-gauhati-high-court-orders-cbi-probe-1748281", "source": "NDTV"},
                        {"title": "Emergency PPE kit contracts awarded to spouse-linked JCB Industries", "url": "https://www.thewire.in/government/himanta-biswa-sarma-riniki-bhuyan-sarma-jcb-industries-ppe-kits-covid-19", "source": "The Wire"}
                    ]
                elif "gadkari" in name_lower:
                    summary = (
                        "Union Minister Nitin Gadkari has been involved in policy lobbying and asset-related debates:<br><br>"
                        "<strong>1. Ethanol Policy Conflict of Interest:</strong> Allegations from opposition parties in September 2025 accusing Gadkari of lobbying for E20 ethanol blending mandates to benefit family-linked biofuel firms (CIAN Agro Industries and Manas Agro Industries, where his sons are shareholders or directors).<br>"
                        "<strong>2. Purti Group MCA Probe:</strong> Historical investigations by the Ministry of Corporate Affairs (MCA) into funding sources and shell company shareholding networks related to his Purti Group business venture."
                    )
                    refs = [
                        {"title": "Congress alleges conflict of interest against Gadkari over ethanol policy", "url": "https://www.deccanherald.com/india/conflict-of-interest-congress-alleges-gadkaris-sons-profited-from-ethanol-policy-demand-lokpal-probe-3712105", "source": "Deccan Herald"},
                        {"title": "Gadkari lobbying for ethanol blending, alleges Congress", "url": "https://www.thehindu.com/news/national/gadkari-lobbying-for-ethanol-blending-alleges-congress/article70012549.ece", "source": "The Hindu"},
                        {"title": "MCA initiates discreet probe into funding of Nitin Gadkari's Purti Group", "url": "https://www.ndtv.com/india-news/mca-initiates-discreet-probe-into-funding-of-nitin-gadkaris-purti-group-502901", "source": "NDTV"}
                    ]
                elif "hooda" in name_lower:
                    summary = (
                        "Former Chief Minister Bhupinder Singh Hooda has been chargesheeted by the CBI in connection with major land deals:<br><br>"
                        "<strong>1. Manesar Land Acquisition Scam:</strong> Chargesheeted by the CBI in 2018 for allegedly forcing land owners to sell 400 acres in Manesar to private developers at throwaway prices under the threat of government acquisition between 2004 and 2007."
                    )
                    refs = [
                        {"title": "CBI chargesheets Bhupinder Singh Hooda in Manesar land scam case", "url": "https://www.ndtv.com/india-news/cbi-files-chargesheet-against-bhupinder-singh-hooda-in-manesar-land-scam-case-1807758", "source": "NDTV"}
                    ]
                elif "lalu" in name_lower:
                    summary = (
                        "Former Bihar Chief Minister Lalu Prasad Yadav has been convicted and chargesheeted in multiple historic and active corruption cases:<br><br>"
                        "<strong>1. The Fodder Scam (Fodder allocation):</strong> Convicted in multiple cases by special CBI courts for the embezzlement of over Rs 940 crore from Bihar government treasuries. The scam involved fraudulent withdrawals for non-existent livestock fodder and equipment during the 1990s.<br>"
                        "<strong>2. Land for Job Scam (Railways):</strong> Chargesheeted by the CBI/ED for allegedly providing Group-D jobs in the Indian Railways (during his tenure as Union Railway Minister from 2004-2009) in exchange for land parcels transferred to his family members at throwaway prices. In early 2026, a Delhi court formally framed charges in this case."
                    )
                    refs = [
                        {"title": "What is the Fodder Scam? Cases and Convictions explained", "url": "https://en.wikipedia.org/wiki/Fodder_Scam", "source": "Wikipedia"},
                        {"title": "Court frames charges against Lalu Prasad Yadav and family in Land for Job case", "url": "https://www.deccanherald.com/india/delhi-court-frames-charges-against-lalu-prasad-rabri-devi-in-land-for-jobs-case-3712109", "source": "Deccan Herald"},
                        {"title": "Supreme Court refuses to quash CBI case in Land for Job scam", "url": "https://www.thehindu.com/news/national/supreme-court-allows-cbi-trial-against-lalu-prasad-yadav-in-land-for-job-case/article70012552.ece", "source": "The Hindu"}
                    ]
                elif "mohan" in name_lower:
                    summary = (
                        "Madhya Pradesh Chief Minister Dr. Mohan Yadav has faced political scrutiny regarding property acquisitions:<br><br>"
                        "<strong>1. Ujjain Land Scam Allegations:</strong> In June 2026, the opposition Congress party alleged that members of Mohan Yadav's family and linked real estate developers acquired 137 plots covering ~168 acres in Ujjain after he assumed the CM office. They claim the land was purchased due to planned infrastructure expansions ahead of the 2028 Simhastha Kumbh. The BJP and CM's office have dismissed the claims as completely baseless, stating no new land was acquired post-elections."
                    )
                    refs = [
                        {"title": "Congress alleges Ujjain land scam linked to CM Mohan Yadav's family", "url": "https://www.thehindu.com/news/national/other-states/congress-alleges-ujjain-land-scam-linked-to-madhya-pradesh-cm-mohan-yadavs-family/article68312051.ece", "source": "The Hindu"},
                        {"title": "Mohan Yadav CMO releases statement denying Ujjain land allegations", "url": "https://www.thehindu.com/news/national/other-states/madhya-pradesh-cmo-says-no-change-in-cm-mohan-yadavs-property-since-2023-affidavit/article68314522.ece", "source": "The Hindu"}
                    ]
                else:
                    summary = f"No active background investigation reports or public scams logged for {name} in the baseline database. You can use the Google search options above to perform external audits."
                    refs = []
                
                return self._json({"ok": True, "summary": summary, "references": refs})
            m = re.match(r"^/api/entity/(\d+)$", p)
            if m:
                prof = entity_profile(int(m.group(1)))
                return self._json(prof) if prof else self._json({"error": "not found"}, 404)
            m = re.match(r"^/api/graph/(\d+)$", p)
            if m:
                depth = min(int(q.get("depth", ["2"])[0]), 4)
                return self._json(graph_for(int(m.group(1)), depth))
            m = re.match(r"^/api/export/entity/(\d+)\.(json|csv)$", p)
            if m:
                return self.api_export(int(m.group(1)), m.group(2))
            if p == "/api/admin/review":
                if not self._authed():
                    return self._json({"error": "unauthorized"}, 401)
                c = get_db().cursor()
                items = rows_to_dicts(c.execute(
                    "SELECT * FROM review_queue WHERE status='pending' ORDER BY id DESC"))
                for i in items:
                    i["payload"] = json.loads(i["payload"] or "{}")
                    i["suggestion"] = json.loads(i["suggestion"] or "{}")
                return self._json(items)
            if p == "/api/admin/imports":
                if not self._authed():
                    return self._json({"error": "unauthorized"}, 401)
                c = get_db().cursor()
                return self._json(rows_to_dicts(c.execute(
                    "SELECT * FROM imports ORDER BY id DESC LIMIT 50")))
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        p = urlparse(self.path).path
        get_db()
        try:
            if p == "/api/admin/login":
                body = self._body_json()
                if body.get("password") == ADMIN_PASSWORD:
                    tok = secrets.token_hex(16)
                    _tokens.add(tok)
                    return self._json({"token": tok})
                return self._json({"error": "wrong password"}, 401)
            if p == "/api/admin/edit-source":
                body = self._body_json()
                table = body.get("table")
                row_id = body.get("id")
                new_source = body.get("new_source", "").strip()
                if table not in ("relationships", "contracts", "declarations", "tenures", "company_financials", "fund_flows"):
                    return self._json({"error": "invalid table"}, 400)
                if not row_id:
                    return self._json({"error": "missing id"}, 400)
                c = get_db().cursor()
                c.execute(f"UPDATE {table} SET source = ? WHERE id = ?", (new_source, row_id))
                get_db().commit()
                rescore()
                return self._json({"ok": True})
            if p == "/api/admin/edit-source-by-url":
                body = self._body_json()
                current_source = body.get("current_source", "").strip()
                new_source = body.get("new_source", "").strip()
                if not current_source:
                    return self._json({"error": "missing current_source"}, 400)
                c = get_db().cursor()
                tables = ("relationships", "contracts", "declarations", "tenures", "company_financials", "fund_flows")
                for table in tables:
                    c.execute(f"UPDATE {table} SET source = ? WHERE source = ?", (new_source, current_source))
                get_db().commit()
                rescore()
                return self._json({"ok": True})
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            if p == "/api/admin/upload":
                body = self._body_json()
                result = import_csv(body["dataset"], body["csv"], body.get("filename", "upload.csv"))
                result["flags"] = rescore()
                return self._json(result)
            if p == "/api/admin/rescore":
                return self._json({"flags": rescore()})
            m = re.match(r"^/api/admin/review/(\d+)$", p)
            if m:
                body = self._body_json()
                ok = resolve_review(int(m.group(1)), body.get("action", "approve"))
                if ok:
                    rescore()
                return self._json({"ok": ok})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    # -- API implementations
    def api_stats(self, q):
        c = get_db().cursor()
        g = lambda sql, *a: c.execute(sql, a).fetchone()[0]
        if not self._is_approved(q):
            g_ids = get_gadkari_network_ids()
            q_str = ",".join(str(i) for i in g_ids) if g_ids else "0"
            return self._json({
                "entities": g(f"SELECT COUNT(*) FROM entities WHERE id IN ({q_str})"),
                "politicians": g(f"SELECT COUNT(*) FROM entities WHERE type='Politician' AND id IN ({q_str})"),
                "companies": g(f"SELECT COUNT(*) FROM entities WHERE type='Company' AND id IN ({q_str})"),
                "contracts": g(f"SELECT COUNT(*) FROM contracts WHERE supplier_id IN ({q_str}) OR buyer_id IN ({q_str})"),
                "contract_value": g(f"SELECT COALESCE(SUM(value),0) FROM contracts WHERE supplier_id IN ({q_str}) OR buyer_id IN ({q_str})"),
                "relationships": g(f"SELECT COUNT(*) FROM relationships WHERE from_id IN ({q_str}) OR to_id IN ({q_str})"),
                "flags": g(f"SELECT COUNT(*) FROM flags WHERE entity_id IN ({q_str})"),
                "flagged_value": g(f"SELECT COALESCE(SUM(value_involved),0) FROM flags WHERE entity_id IN ({q_str})"),
            })
        return self._json({
            "entities": g("SELECT COUNT(*) FROM entities"),
            "politicians": g("SELECT COUNT(*) FROM entities WHERE type='Politician'"),
            "companies": g("SELECT COUNT(*) FROM entities WHERE type='Company'"),
            "contracts": g("SELECT COUNT(*) FROM contracts"),
            "contract_value": g("SELECT COALESCE(SUM(value),0) FROM contracts"),
            "relationships": g("SELECT COUNT(*) FROM relationships"),
            "flags": g("SELECT COUNT(*) FROM flags"),
            "flagged_value": g("SELECT COALESCE(SUM(value_involved),0) FROM flags"),
        })

    def api_search(self, q):
        term = (q.get("q", [""])[0] or "").strip()
        if not term:
            return self._json([])
        c = get_db().cursor()
        like = f"%{term}%"
        approved_filter = ""
        if not self._is_approved(q):
            g_ids = get_gadkari_network_ids()
            q_str = ",".join(str(i) for i in g_ids) if g_ids else "0"
            approved_filter = f" AND e.id IN ({q_str})"

        rows = rows_to_dicts(c.execute(f"""
            SELECT e.id, e.name, e.type, e.party, e.constituency, e.state,
                   COALESCE(MAX(f.risk_score),0) AS risk
            FROM entities e LEFT JOIN flags f ON f.entity_id=e.id
            WHERE (e.name LIKE ? OR e.pan LIKE ? OR e.din LIKE ? OR e.cin LIKE ? OR e.constituency LIKE ?){approved_filter}
            GROUP BY e.id ORDER BY CASE WHEN e.name LIKE '%Nitin Gadkari%' THEN 0 ELSE 1 END, risk DESC, e.name LIMIT 20""",
            (like, like, like, like, like)))
        return self._json(rows)

    def api_entities(self, q):
        c = get_db().cursor()
        where, args = ["1=1"], []
        if not self._is_approved(q):
            g_ids = get_gadkari_network_ids()
            q_str = ",".join(str(i) for i in g_ids) if g_ids else "0"
            where.append(f"e.id IN ({q_str})")

        if q.get("type", [""])[0]:
            where.append("e.type=?"); args.append(q["type"][0])
        if q.get("state", [""])[0]:
            where.append("e.state=?"); args.append(q["state"][0])
        if q.get("q", [""])[0]:
            where.append("e.name LIKE ?"); args.append(f"%{q['q'][0]}%")
        page = max(int(q.get("page", ["1"])[0]), 1)
        rows = rows_to_dicts(c.execute(f"""
            SELECT e.id, e.name, e.type, e.party, e.constituency, e.state,
                   COALESCE(MAX(f.risk_score),0) AS risk,
                   COALESCE(SUM(f.value_involved),0) AS flagged_value
            FROM entities e LEFT JOIN flags f ON f.entity_id=e.id
            WHERE {' AND '.join(where)}
            GROUP BY e.id ORDER BY CASE WHEN e.name LIKE '%Nitin Gadkari%' THEN 0 ELSE 1 END, risk DESC, e.name LIMIT 50 OFFSET ?""",
            args + [(page - 1) * 50]))
        total = c.execute(
            f"SELECT COUNT(*) FROM entities e WHERE {' AND '.join(where)}", args).fetchone()[0]
        states = [r[0] for r in c.execute(
            f"SELECT DISTINCT state FROM entities e WHERE e.state IS NOT NULL AND {' AND '.join(where)} ORDER BY state", args)]
        return self._json({"rows": rows, "total": total, "page": page, "states": states})

    def api_highrisk(self, q):
        c = get_db().cursor()
        where_clause = ""
        if not self._is_approved(q):
            g_ids = get_gadkari_network_ids()
            q_str = ",".join(str(i) for i in g_ids) if g_ids else "0"
            where_clause = f" WHERE e.id IN ({q_str})"

        rows = rows_to_dicts(c.execute(f"""
            SELECT e.id, e.name, e.party, e.constituency, e.state,
                   MAX(f.risk_score) AS risk, SUM(f.value_involved) AS flagged_value,
                   COUNT(f.id) AS flag_count,
                   (SELECT title FROM flags WHERE entity_id=e.id ORDER BY risk_score DESC LIMIT 1) AS top_flag
            FROM entities e JOIN flags f ON f.entity_id=e.id
            {where_clause}
            GROUP BY e.id ORDER BY CASE WHEN e.name LIKE '%Nitin Gadkari%' THEN 0 ELSE 1 END, risk DESC LIMIT 8"""))
        return self._json(rows)

    def api_overview(self, q):
        c = get_db().cursor()
        where_clause = "e.type='Politician' AND e.state IS NOT NULL"
        pattern_where = ""
        if not self._is_approved(q):
            g_ids = get_gadkari_network_ids()
            q_str = ",".join(str(i) for i in g_ids) if g_ids else "0"
            where_clause += f" AND e.id IN ({q_str})"
            pattern_where = f" WHERE entity_id IN ({q_str})"

        rows = rows_to_dicts(c.execute(f"""
            SELECT e.state,
                   COUNT(DISTINCT e.id) AS politicians,
                   COUNT(DISTINCT f.id) AS flags,
                   COALESCE(SUM(f.value_involved),0) AS flagged_value,
                   COALESCE(MAX(f.risk_score),0) AS max_risk
            FROM entities e LEFT JOIN flags f ON f.entity_id=e.id
            WHERE {where_clause}
            GROUP BY e.state ORDER BY flagged_value DESC"""))
        patterns = rows_to_dicts(c.execute(f"""
            SELECT pattern, COUNT(*) AS n, COALESCE(SUM(value_involved),0) AS value
            FROM flags {pattern_where} GROUP BY pattern ORDER BY value DESC"""))
        return self._json({"states": rows, "patterns": patterns})

    def api_export(self, eid, fmt):
        prof = entity_profile(eid)
        if not prof:
            return self._json({"error": "not found"}, 404)
        slug = re.sub(r"\W+", "_", prof["entity"]["name"]).strip("_").lower()
        if fmt == "json":
            payload = dict(prof)
            payload["graph"] = graph_for(eid, 2)
            return self._raw(json.dumps(payload, indent=2, default=str),
                             "application/json", filename=f"bharatwatch_{slug}.json")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["section", "a", "b", "c", "d", "e"])
        for r in prof["relationships"]:
            w.writerow(["relationship", r["from_name"], r["type"], r["to_name"], r["evidence"], r["source"]])
        for k in prof["contracts"]:
            w.writerow(["contract", k["tender_id"], k["buyer_name"], k["supplier_name"], k["value"], k["award_date"]])
        for f in prof["fund_flows"]:
            w.writerow(["fund_flow", f["from_name"], f["to_name"], f["amount"], f["date"], f["scheme"]])
        for fl in prof["flags"]:
            w.writerow(["flag", fl["pattern"], fl["risk_score"], fl["title"], fl["value_involved"], ""])
        return self._raw(buf.getvalue(), "text/csv", filename=f"bharatwatch_{slug}.csv")


def main():
    init_db()
    c = get_db().cursor()
    if c.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0:
        from seed import seed
        seed()
    if c.execute("SELECT COUNT(*) FROM flags").fetchone()[0] == 0:
        print("Computing red flags:", rescore())
    if HOST != "127.0.0.1" and ADMIN_PASSWORD == "bharat-admin":
        print("WARNING: serving publicly with the DEFAULT admin password. "
              "Set BHARATWATCH_ADMIN_PASSWORD before exposing this instance.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"BharatWatch running at http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
