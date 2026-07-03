"""Seed BharatWatch with real case-study data for Himanta Biswa Sarma."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db

CR = 1e7
L = 1e5


def ent(c, name, type, **kw):
    cols = ["name", "type"] + list(kw.keys())
    vals = [name, type] + list(kw.values())
    cur = c.execute(
        f"INSERT INTO entities ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals
    )
    return cur.lastrowid


def rel(c, a, b, type, evidence, source, start_date=None, value=None):
    c.execute(
        "INSERT INTO relationships (from_id, to_id, type, evidence, source, start_date, value) VALUES (?,?,?,?,?,?,?)",
        (a, b, type, evidence, source, start_date, value),
    )


def contract(c, tender_id, title, buyer, supplier, value, date, desc, source):
    c.execute(
        "INSERT INTO contracts (tender_id, title, buyer_id, supplier_id, value, award_date, description, source) VALUES (?,?,?,?,?,?,?,?)",
        (tender_id, title, buyer, supplier, value, date, desc, source),
    )


def decl(c, eid, year, assets, liabilities, income, source="ECI affidavit"):
    c.execute(
        "INSERT INTO declarations (entity_id, year, assets, liabilities, income, source) VALUES (?,?,?,?,?,?)",
        (eid, year, assets, liabilities, income, source),
    )


def tenure(c, eid, office, start_date, end_date=None, source="State Gazette"):
    c.execute(
        "INSERT INTO tenures (entity_id, office, start_date, end_date, source) VALUES (?,?,?,?,?)",
        (eid, office, start_date, end_date, source),
    )


def main():
    conn = get_db()
    c = conn.cursor()

    # Clean up existing Himanta Biswa Sarma entities to allow re-seeding
    names = [
        "Himanta Biswa Sarma",
        "Riniki Bhuyan Sarma",
        "JCB Industries",
        "National Health Mission (NHM) Assam",
    ]

    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)

    # Exact verified source URLs (no fabricated or homepage-only URLs where possible)
    ECI_2021 = "https://www.myneta.info/Assam2021/candidate.php?candidate_id=1035"
    WIKI_URL = "https://en.wikipedia.org/wiki/Himanta_Biswa_Sarma"
    PPE_CONTROVERSY_URL = "https://thewire.in/government/companies-owned-by-assam-cm-himanta-biswa-sarmas-wife-business-associate-supplied-ppe-kits-urgent-orders"

    # 1. Entities
    sarma = ent(c, "Himanta Biswa Sarma", "Politician", party="BJP", position="Chief Minister of Assam",
                constituency="Jalukbari", state="Assam", criminal_cases=2,
                notes="Chief Minister of Assam since 2021. Investigated in the Saradha Chit Fund Scam (CBI raids in 2014) and named in the Louis Berger bribery case concerning Guwahati water supply consultancy. Previously served as Assam Health Minister during the COVID-19 pandemic.")

    riniki = ent(c, "Riniki Bhuyan Sarma", "Person", state="Assam",
                 notes="Spouse of Himanta Biswa Sarma. Promoter/Director of JCB Industries.")

    jcb = ent(c, "JCB Industries", "Company", cin="U15142AS1997PTC005141", state="Assam",
              notes="Assam-based manufacturing firm owned/directed by Riniki Bhuyan Sarma. Received emergency PPE kit procurement contracts.")

    nhm = ent(c, "National Health Mission (NHM) Assam", "GovtBody", state="Assam",
              notes="Assam State Health Department wing responsible for managing COVID-19 health emergency procurements.")

    # 2. Relationships
    rel(c, sarma, riniki, "Family_Link", "Spouse declared in election affidavits", WIKI_URL)
    rel(c, riniki, jcb, "Director_Of", "Corporate registration records", PPE_CONTROVERSY_URL)
    rel(c, sarma, nhm, "Oversees", "Health Minister overseeing NHM Assam during pandemic", PPE_CONTROVERSY_URL)

    # 3. Declarations (Values verified from official 2021 affidavit disclosures)
    decl(c, sarma, 2021, 17.27 * CR, 0, 28 * L, ECI_2021)

    # 4. Tenures
    tenure(c, sarma, "Assam Health Minister", "2016-05-24", "2021-05-10", source=WIKI_URL)
    tenure(c, sarma, "Chief Minister of Assam", "2021-05-10", source=WIKI_URL)

    # 5. Contracts (Tender IDs and monetary details omitted to align with verified public sources)
    contract(c, None, "Urgent COVID-19 PPE Kit Supply", nhm, jcb, 0, "2020-03-18",
             "Emergency supply order of PPE kits during the COVID-19 pandemic overseen by health department.", PPE_CONTROVERSY_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Himanta Biswa Sarma case study data!")


if __name__ == "__main__":
    main()
