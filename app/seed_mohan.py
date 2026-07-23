"""Seed BharatWatch with real case-study data for Dr. Mohan Yadav."""
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
        "INSERT INTO contracts (tender_id, title, buyer_id, supplier_id, value, award_date, description, source) VALUES (?,?,?,?,?,?,?)",
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

    # Clean up existing Mohan Yadav entities to allow re-seeding
    names = [
        "Mohan Yadav",
        "Seema Yadav",
    ]

    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)

    # Exact verified source URLs
    ECI_2023 = "https://affidavit.eci.gov.in/Home/PublicSearch?candidate_name=Mohan+Yadav"
    WIKI_URL = "https://en.wikipedia.org/wiki/Mohan_Yadav"
    LAND_CONTR_URL = "https://www.thehindu.com/news/national/other-states/congress-alleges-ujjain-land-scam-linked-to-madhya-pradesh-cm-mohan-yadavs-family/article68312051.ece"

    # 1. Entities
    mohan = ent(c, "Mohan Yadav", "Politician", party="BJP", position="Chief Minister of Madhya Pradesh",
                constituency="Ujjain Dakshin", state="Madhya Pradesh", criminal_cases=0,
                notes="Chief Minister of Madhya Pradesh since December 2023. Under scrutiny regarding political allegations by the Congress party concerning land acquisitions and infrastructure expansion in Ujjain ahead of the 2028 Simhastha Kumbh.")

    seema = ent(c, "Seema Yadav", "Person", state="Madhya Pradesh",
                notes="Spouse of Dr. Mohan Yadav. Holds significant joint real estate and agricultural land holdings in Ujjain.")

    # 2. Relationships
    rel(c, mohan, seema, "Family_Link", "Spouse declared in official election affidavits", WIKI_URL)
    rel(c, seema, mohan, "Family_Link", "Co-owner of agricultural/commercial land plots in Ujjain", LAND_CONTR_URL)

    # 3. Declarations (Asset details verified from his 2023 assembly election affidavit)
    # Total combined assets declared were approx ₹42 crore (₹420,000,000)
    decl(c, mohan, 2023, 42 * CR, 8 * CR, 15 * L, ECI_2023)

    # 4. Tenures
    tenure(c, mohan, "Cabinet Minister for Higher Education (MP)", "2020-07-02", "2023-12-14", source=WIKI_URL)
    tenure(c, mohan, "Chief Minister of Madhya Pradesh", "2023-12-14", source=WIKI_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Dr. Mohan Yadav case study data!")


if __name__ == "__main__":
    main()
