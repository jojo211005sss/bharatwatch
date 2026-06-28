"""CSV ingestion for BharatWatch admin portal.

Supported datasets (CSV headers, case-insensitive):
  affidavits : name,pan,party,position,constituency,state,year,assets,liabilities,income,criminal_cases
  companies  : cin,name,pan,address,state,incorporation_date
  directors  : din,name,pan,cin,company_name,appointment_date
  contracts  : tender_id,title,buyer,supplier,supplier_cin,value,award_date,description,source
  fundflows  : scheme,from,to,amount,date,purpose,source
  relations  : from_name,to_name,type,evidence,source

Dataset Types to Source Domain Mappings:
  affidavits  -> ECI (affidavit.eci.gov.in) / MyNeta (myneta.info)
  companies   -> MCA (mca.gov.in) / ZaubaCorp (zaubacorp.com) / data.gov.in
  directors   -> MCA (mca.gov.in) / data.gov.in
  contracts   -> CPPP (eprocure.gov.in) / GeM (gem.gov.in) / SPPP (sppp.rajasthan.gov.in)
  fundflows   -> PFMS (pfms.nic.in) / MPLADS (mplads.gov.in)
  relations   -> any secondary source (e.g. ndtv.com, thehindu.com, wikipedia.org)
  financials  -> MCA filings
  tenures     -> Sansad.in (sansad.in) / state gazette

Rows that resolve confidently are written directly; grey-zone matches go to
the review queue (optionally adjudicated by Claude via resolve.ai_adjudicate).
"""
import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db
from resolve import find_entity, ai_adjudicate
from verify_sources import PRIMARY_DOMAINS, SECONDARY_DOMAINS
from urllib.parse import urlparse

def validate_source(url: str):
    """Validate that a source URL belongs to an allowed domain.
    Raises ValueError if the URL is missing or its domain is not in the allowed sets.
    """
    if not url or not url.startswith("http"):
        raise ValueError(f"Invalid source URL: {url}")
    domain = urlparse(url).netloc
    bare_domain = domain.removeprefix("www.")
    # Concession for wikipedia or other common source platforms if needed, but match verify_sources
    if (domain not in PRIMARY_DOMAINS and domain not in SECONDARY_DOMAINS and
        bare_domain not in PRIMARY_DOMAINS and bare_domain not in SECONDARY_DOMAINS and
        "wikipedia.org" not in domain and "wikipedia.org" not in bare_domain):
        raise ValueError(f"Unsupported source domain '{domain}' in URL {url}")
DATASETS = ("affidavits", "companies", "directors", "contracts", "fundflows", "relations", "financials", "tenures")


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip() or 0)
    except ValueError:
        return 0.0


def _get_or_create(c, row, etype, source):
    eid, conf, method = find_entity(row, etype)
    if eid and method != "grey":
        return eid, False
    if eid and method == "grey":
        verdict = ai_adjudicate(row, _entity_name(c, eid))
        if verdict is True:
            return eid, False
        if verdict is None:
            kind = f"match_{etype.lower()}" if etype else "match_entity"
            c.execute(
                "INSERT INTO review_queue (kind, payload, suggestion, confidence) VALUES (?,?,?,?)",
                (kind, json.dumps(row),
                 json.dumps({"candidate_id": eid, "candidate_name": _entity_name(c, eid)}), conf),
            )
            return None, False
        # verdict is False → distinct entity, fall through to create

    etype_to_save = etype
    if not etype_to_save:
        name_lower = row.get("name", "").lower()
        if any(w in name_lower for w in ["pvt", "ltd", "private", "limited", "llp", "industries", "builders", "constructions", "suppliers", "traders", "ventures"]):
            etype_to_save = "Company"
        elif any(w in name_lower for w in ["department", "dept", "board", "authority", "panchayat", "ministry", "commission", "office"]):
            etype_to_save = "GovtBody"
        elif any(w in name_lower for w in ["trust", "foundation", "charity", "seva"]):
            etype_to_save = "Trust"
        else:
            etype_to_save = "Person"

    cur = c.execute(
        "INSERT INTO entities (name, type, pan, din, cin, party, position, constituency, state, address, incorporation_date, criminal_cases, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (row.get("name", "").strip(), etype_to_save, row.get("pan") or None, row.get("din") or None,
         row.get("cin") or None, row.get("party"), row.get("position"), row.get("constituency"),
         row.get("state"), row.get("address"), row.get("incorporation_date"),
         int(_num(row.get("criminal_cases"))), f"Imported from {source}"),
    )
    return cur.lastrowid, True


def _entity_name(c, eid):
    r = c.execute("SELECT name FROM entities WHERE id=?", (eid,)).fetchone()
    return r["name"] if r else ""


def import_csv(dataset, csv_text, filename="upload.csv"):
    if dataset not in DATASETS:
        raise ValueError(f"Unknown dataset '{dataset}'. Expected one of {DATASETS}")
    conn = get_db()
    c = conn.cursor()
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in reader]
    accepted = queued = 0
    q_before = c.execute("SELECT COUNT(*) FROM review_queue WHERE status='pending'").fetchone()[0]

    for row in rows:
        src = row.get("source") or f"{dataset} CSV ({filename})"
        # Validate source URL if provided
        try:
            validate_source(src)
        except ValueError as e:
            # Queue invalid source for review
            c.execute(
                "INSERT INTO review_queue (kind, payload, suggestion, confidence) VALUES (?,?,?,?)",
                ("invalid_source", json.dumps(row), json.dumps({"error": str(e)}), 0),
            )
            queued += 1
            continue
        if dataset == "affidavits":
            eid, _ = _get_or_create(c, row, "Politician", src)
            if eid is None:
                continue
            if row.get("year"):
                c.execute(
                    "INSERT INTO declarations (entity_id, year, assets, liabilities, income, source) VALUES (?,?,?,?,?,?)",
                    (eid, int(_num(row["year"])), _num(row.get("assets")), _num(row.get("liabilities")),
                     _num(row.get("income")), src))
            accepted += 1

        elif dataset == "companies":
            eid, _ = _get_or_create(c, row, "Company", src)
            accepted += 1 if eid else 0

        elif dataset == "directors":
            person, _ = _get_or_create(c, {"name": row.get("name"), "din": row.get("din"),
                                           "pan": row.get("pan")}, "Person", src)
            comp, _ = _get_or_create(c, {"name": row.get("company_name"), "cin": row.get("cin")},
                                     "Company", src)
            if person and comp:
                c.execute(
                    "INSERT INTO relationships (from_id, to_id, type, evidence, source, start_date) VALUES (?,?,?,?,?,?)",
                    (person, comp, "Director_Of",
                     f"DIN {row.get('din', '?')} appointed {row.get('appointment_date', '?')}", src,
                     row.get("appointment_date")))
                accepted += 1

        elif dataset == "contracts":
            buyer, _ = _get_or_create(c, {"name": row.get("buyer")}, "GovtBody", src)
            supplier, _ = _get_or_create(c, {"name": row.get("supplier"), "cin": row.get("supplier_cin")},
                                         "Company", src)
            if buyer and supplier:
                c.execute(
                    "INSERT INTO contracts (tender_id, title, buyer_id, supplier_id, value, award_date, description, source) VALUES (?,?,?,?,?,?,?,?)",
                    (row.get("tender_id"), row.get("title"), buyer, supplier, _num(row.get("value")),
                     row.get("award_date"), row.get("description"), src))
                accepted += 1

        elif dataset == "fundflows":
            frm, _ = _get_or_create(c, {"name": row.get("from")}, "GovtBody", src)
            to, _ = _get_or_create(c, {"name": row.get("to")}, "GovtBody", src)
            if frm and to:
                c.execute(
                    "INSERT INTO fund_flows (scheme, from_id, to_id, amount, date, purpose, source) VALUES (?,?,?,?,?,?,?)",
                    (row.get("scheme"), frm, to, _num(row.get("amount")), row.get("date"),
                     row.get("purpose"), src))
                accepted += 1

        elif dataset == "relations":
            a, _ = _get_or_create(c, {"name": row.get("from_name")}, None, src)
            b, _ = _get_or_create(c, {"name": row.get("to_name")}, None, src)
            if a and b and row.get("type"):
                c.execute(
                    "INSERT INTO relationships (from_id, to_id, type, evidence, source) VALUES (?,?,?,?,?)",
                    (a, b, row["type"], row.get("evidence"), src))
                accepted += 1

        elif dataset == "financials":
            comp, _ = _get_or_create(c, {"name": row.get("company_name"), "cin": row.get("cin")}, "Company", src)
            if comp and row.get("year"):
                c.execute(
                    "INSERT OR REPLACE INTO company_financials (company_id, year, assets, liabilities, revenue, net_profit, source) VALUES (?,?,?,?,?,?,?)",
                    (comp, int(_num(row["year"])), _num(row.get("assets")), _num(row.get("liabilities")),
                     _num(row.get("revenue")), _num(row.get("net_profit")), src))
                accepted += 1

        elif dataset == "tenures":
            pol, _ = _get_or_create(c, {"name": row.get("politician_name"), "pan": row.get("pan")}, "Politician", src)
            if pol and row.get("office") and row.get("start_date"):
                c.execute(
                    "INSERT INTO tenures (entity_id, office, start_date, end_date, source) VALUES (?,?,?,?,?)",
                    (pol, row["office"].strip(), row["start_date"].strip(), row.get("end_date") or None, src))
                accepted += 1

    queued = c.execute("SELECT COUNT(*) FROM review_queue WHERE status='pending'").fetchone()[0] - q_before
    c.execute(
        "INSERT INTO imports (filename, dataset, rows, accepted, queued, summary) VALUES (?,?,?,?,?,?)",
        (filename, dataset, len(rows), accepted, queued,
         f"{accepted}/{len(rows)} rows imported, {queued} sent to review queue"))
    conn.commit()
    return {"rows": len(rows), "accepted": accepted, "queued": queued}


def resolve_review(item_id, action):
    """Approve (merge into candidate) or reject (create new entity) a queue item."""
    conn = get_db()
    c = conn.cursor()
    item = c.execute("SELECT * FROM review_queue WHERE id=?", (item_id,)).fetchone()
    if not item or item["status"] != "pending":
        return False
    row = json.loads(item["payload"])
    if action == "reject":
        # treat as a distinct new entity
        etype = item["kind"].replace("match_", "").capitalize()
        c.execute(
            "INSERT INTO entities (name, type, pan, din, cin, state, notes) VALUES (?,?,?,?,?,?,?)",
            (row.get("name", ""), etype, row.get("pan"), row.get("din"), row.get("cin"),
             row.get("state"), "Created from rejected merge in review queue"))
    c.execute("UPDATE review_queue SET status=? WHERE id=?",
              ("approved" if action == "approve" else "rejected", item_id))
    conn.commit()
    return True
