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
         "/overview": "overview.html", "/about": "about.html", "/admin": "admin.html"}


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


def entity_profile(eid):
    c = get_db().cursor()
    e = c.execute("SELECT * FROM entities WHERE id=?", (eid,)).fetchone()
    if not e:
        return None
    decls = rows_to_dicts(c.execute(
        "SELECT * FROM declarations WHERE entity_id=? ORDER BY year", (eid,)))
    flags = rows_to_dicts(c.execute(
        "SELECT * FROM flags WHERE entity_id=? ORDER BY risk_score DESC", (eid,)))
    for f in flags:
        f["evidence"] = json.loads(f["evidence"] or "[]")
    rels = rows_to_dicts(c.execute("""
        SELECT r.*, a.name AS from_name, b.name AS to_name
        FROM relationships r JOIN entities a ON a.id=r.from_id JOIN entities b ON b.id=r.to_id
        WHERE r.from_id=? OR r.to_id=?""", (eid, eid)))
    # Find all first-degree personal connections of eid (Family, Friends, Associates, etc.)
    personal_connections = {eid: {"name": e["name"], "rel_to_pol": "Self"}}
    personal_rel_types = {'family_link', 'friend_link', 'associate', 'spouse', 'son', 'daughter', 'child', 'parent', 'sibling', 'brother', 'sister', 'wife', 'husband', 'relative'}
    
    rows = c.execute("""
        SELECT r.from_id, r.to_id, r.type, r.evidence
        FROM relationships r
        WHERE r.from_id = ? OR r.to_id = ?
    """, (eid, eid)).fetchall()
    
    for r in rows:
        other_id = r["to_id"] if r["from_id"] == eid else r["from_id"]
        oth = c.execute("SELECT name, type FROM entities WHERE id = ?", (other_id,)).fetchone()
        if oth:
            oth_type = oth["type"]
            if oth_type in ("Person", "Politician") or r["type"].lower() in personal_rel_types:
                desc = f"{r['type']}"
                if r['evidence']:
                    desc += f" ({r['evidence']})"
                personal_connections[other_id] = {
                    "name": oth["name"],
                    "rel_to_pol": desc
                }

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
                via_desc = f"{p_info['name']}"
                if p_id != eid:
                    via_desc += f" [{p_info['rel_to_pol']}]"
                via_desc += f" — {r['type']}"
                if r['evidence']:
                    via_desc += f" ({r['evidence']})"
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
        SELECT k.*, b.name AS buyer_name, s.name AS supplier_name FROM contracts k
        JOIN entities b ON b.id=k.buyer_id JOIN entities s ON s.id=k.supplier_id
        WHERE k.supplier_id IN ({qc}) OR k.buyer_id=? ORDER BY k.award_date""",
        tuple(comp_ids) + (eid,)))
    net_ids = tuple(personal_connections.keys()) + tuple(comp_ids)
    qn = ",".join("?" * len(net_ids))
    flows = rows_to_dicts(c.execute(f"""
        SELECT f.*, a.name AS from_name, b.name AS to_name FROM fund_flows f
        JOIN entities a ON a.id=f.from_id JOIN entities b ON b.id=f.to_id
        WHERE f.from_id IN ({qn}) OR f.to_id IN ({qn}) ORDER BY f.date""", net_ids + net_ids))
    tenures = rows_to_dicts(c.execute(
        "SELECT * FROM tenures WHERE entity_id=? ORDER BY start_date", (eid,)))
    financials = rows_to_dicts(c.execute(
        "SELECT * FROM company_financials WHERE company_id=? ORDER BY year", (eid,)))
    
    timeline = []
    for d in decls:
        timeline.append({"date": f"{d['year']}-01-01", "kind": "Affidavit",
                         "text": f"Declared assets ₹{d['assets'] / 1e7:.1f} Cr (income ₹{d['income'] / 1e5:.0f} L/yr)"})
    for co in companies:
        if co.get("incorporation_date"):
            timeline.append({"date": co["incorporation_date"], "kind": "Company",
                             "text": f"{co['name']} incorporated (director: {co['via']})"})
    for k in contracts:
        if k.get("award_date"):
            timeline.append({"date": k["award_date"], "kind": "Contract",
                             "text": f"{k['supplier_name']} awarded {k['tender_id']} (₹{k['value'] / 1e7:.1f} Cr) by {k['buyer_name']}"})
    for f in flows:
        if f.get("date"):
            timeline.append({"date": f["date"], "kind": "Fund flow",
                             "text": f"₹{f['amount'] / 1e7:.1f} Cr: {f['from_name']} → {f['to_name']} ({f['scheme']})"})
    for t in tenures:
        timeline.append({"date": t["start_date"], "kind": "Tenure",
                         "text": f"Assumed office: {t['office']}"})
        if t.get("end_date"):
            timeline.append({"date": t["end_date"], "kind": "Tenure",
                             "text": f"Left office: {t['office']}"})
    for fn in financials:
        timeline.append({"date": f"{fn['year']}-03-31", "kind": "Financials",
                         "text": f"Balance sheet FY{fn['year']}: Revenue ₹{fn['revenue'] / 1e7:.1f} Cr, Assets ₹{fn['assets'] / 1e7:.1f} Cr"})
        
    timeline.sort(key=lambda t: t["date"])
    source_dir = find_source_directory_for_entity(e["name"])
    source_files = []
    if source_dir:
        dir_path = os.path.join(ROOT, source_dir)
        if os.path.exists(dir_path):
            for f in sorted(os.listdir(dir_path)):
                if f.endswith('.csv'):
                    source_files.append({
                        "name": f,
                        "path": f"{source_dir}/{f}"
                    })
                    
    risk = max([f["risk_score"] for f in flags], default=0)
    return {"entity": dict(e), "declarations": decls, "flags": flags, "risk": risk,
            "relationships": rels, "companies": companies, "contracts": contracts,
            "fund_flows": flows, "timeline": timeline,
            "flagged_value": sum(f["value_involved"] or 0 for f in flags),
            "tenures": tenures, "financials": financials,
            "source_dir": source_dir, "source_files": source_files}


# ---------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    server_version = "BharatWatch/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # -- responses
    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _raw(self, body, ctype, code=200, filename=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
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
            self._raw(f.read(), MIME.get(ext, "application/octet-stream"))

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
                return self.api_stats()
            if p == "/api/search":
                return self.api_search(q)
            if p == "/api/entities":
                return self.api_entities(q)
            if p == "/api/highrisk":
                return self.api_highrisk()
            if p == "/api/overview":
                return self.api_overview()
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
    def api_stats(self):
        c = get_db().cursor()
        g = lambda sql, *a: c.execute(sql, a).fetchone()[0]
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
        rows = rows_to_dicts(c.execute("""
            SELECT e.id, e.name, e.type, e.party, e.constituency, e.state,
                   COALESCE(MAX(f.risk_score),0) AS risk
            FROM entities e LEFT JOIN flags f ON f.entity_id=e.id
            WHERE e.name LIKE ? OR e.pan LIKE ? OR e.din LIKE ? OR e.cin LIKE ? OR e.constituency LIKE ?
            GROUP BY e.id ORDER BY risk DESC, e.name LIMIT 20""",
            (like, like, like, like, like)))
        return self._json(rows)

    def api_entities(self, q):
        c = get_db().cursor()
        where, args = ["1=1"], []
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
            GROUP BY e.id ORDER BY risk DESC, e.name LIMIT 50 OFFSET ?""",
            args + [(page - 1) * 50]))
        total = c.execute(
            f"SELECT COUNT(*) FROM entities e WHERE {' AND '.join(where)}", args).fetchone()[0]
        states = [r[0] for r in c.execute(
            "SELECT DISTINCT state FROM entities WHERE state IS NOT NULL ORDER BY state")]
        return self._json({"rows": rows, "total": total, "page": page, "states": states})

    def api_highrisk(self):
        c = get_db().cursor()
        rows = rows_to_dicts(c.execute("""
            SELECT e.id, e.name, e.party, e.constituency, e.state,
                   MAX(f.risk_score) AS risk, SUM(f.value_involved) AS flagged_value,
                   COUNT(f.id) AS flag_count,
                   (SELECT title FROM flags WHERE entity_id=e.id ORDER BY risk_score DESC LIMIT 1) AS top_flag
            FROM entities e JOIN flags f ON f.entity_id=e.id
            GROUP BY e.id ORDER BY risk DESC LIMIT 8"""))
        return self._json(rows)

    def api_overview(self):
        c = get_db().cursor()
        rows = rows_to_dicts(c.execute("""
            SELECT e.state,
                   COUNT(DISTINCT e.id) AS politicians,
                   COUNT(DISTINCT f.id) AS flags,
                   COALESCE(SUM(f.value_involved),0) AS flagged_value,
                   COALESCE(MAX(f.risk_score),0) AS max_risk
            FROM entities e LEFT JOIN flags f ON f.entity_id=e.id
            WHERE e.type='Politician' AND e.state IS NOT NULL
            GROUP BY e.state ORDER BY flagged_value DESC"""))
        patterns = rows_to_dicts(c.execute("""
            SELECT pattern, COUNT(*) AS n, COALESCE(SUM(value_involved),0) AS value
            FROM flags GROUP BY pattern ORDER BY value DESC"""))
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
