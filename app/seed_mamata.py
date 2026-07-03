"""Seed BharatWatch with real case-study data for Mamata Banerjee."""
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

    # Clean up existing Mamata Banerjee entities to allow re-seeding
    names = [
        "Mamata Banerjee",
        "Partha Chatterjee",
        "West Bengal School Service Commission (SSC)",
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
    ECI_2021 = "https://www.myneta.info/WestBengal2021/candidate.php?candidate_id=271"
    WIKI_URL = "https://en.wikipedia.org/wiki/Mamata_Banerjee"
    SSC_SCAM_URL = "https://en.wikipedia.org/wiki/2022_West_Bengal_School_Service_Commission_recruitment_scam"

    # 1. Entities
    mamata = ent(c, "Mamata Banerjee", "Politician", party="AITC", position="Chief Minister of West Bengal",
                 constituency="Bhabanipur", state="West Bengal", criminal_cases=0,
                 notes="Chief Minister of West Bengal since 2011. Under political scrutiny regarding the West Bengal School Service Commission (SSC) recruitment scam and CBI/ED money laundering probes in the state.")

    partha = ent(c, "Partha Chatterjee", "Politician", party="AITC", state="West Bengal",
                 notes="Former West Bengal Education Minister. Arrested by the Enforcement Directorate (ED) in July 2022 in connection with the School Service Commission (SSC) recruitment scam.")

    ssc = ent(c, "West Bengal School Service Commission (SSC)", "GovtBody", state="West Bengal",
              notes="Government body responsible for recruiting teaching and non-teaching staff in state-run schools.")

    # 2. Relationships
    rel(c, mamata, partha, "Associate", "Cabinet Minister in the West Bengal Government under Chief Minister Mamata Banerjee", SSC_SCAM_URL)
    rel(c, mamata, ssc, "Oversees", "Chief Minister of West Bengal exercising administrative control over state departments", SSC_SCAM_URL)
    rel(c, partha, ssc, "Oversees", "Education Minister overseeing recruitment boards", SSC_SCAM_URL)

    # 3. Declarations (Asset details verified from her 2021 assembly election affidavit)
    decl(c, mamata, 2021, 15.38 * L, 0, 1.1 * L, ECI_2021)

    # 4. Tenures
    tenure(c, mamata, "Chief Minister of West Bengal", "2011-05-20", source=WIKI_URL)
    tenure(c, partha, "Minister of Education (West Bengal)", "2014-05-27", "2021-05-10", source=WIKI_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Mamata Banerjee case study data!")


if __name__ == "__main__":
    main()
