"""Seed BharatWatch with real case-study data for Pralhad Joshi."""
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

    # Clean up existing Pralhad Joshi entities to allow re-seeding
    names = ["Pralhad Joshi", "Jyoti Joshi", "Gopal Joshi"]

    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)

    # Exact source URLs
    ECI_2024 = "https://www.myneta.info/LokSabha2024/candidate.php?candidate_id=3567"
    ECI_2019 = "https://www.myneta.info/LokSabha2019/candidate.php?candidate_id=10408"
    ECI_2014 = "https://www.myneta.info/ls2014/candidate.php?candidate_id=1075"

    WIKI_URL = "https://en.wikipedia.org/wiki/Pralhad_Joshi"
    NDTV_URL = "https://www.ndtv.com/india-news/union-minister-pralhad-joshis-brother-gopal-joshi-booked-for-cheating-former-mlas-wife-6816568"

    # 1. Entities
    joshi = ent(c, "Pralhad Joshi", "Politician", party="BJP", position="Union Minister of New and Renewable Energy",
                constituency="Dharwad", state="Karnataka", criminal_cases=0,
                notes="Union Minister of New and Renewable Energy; former Minister of Coal, Mines and Parliamentary Affairs. Represents Dharwad constituency in Karnataka.")

    jyoti = ent(c, "Jyoti Joshi", "Person", state="Karnataka",
                notes="Spouse of Pralhad Joshi")

    gopal = ent(c, "Gopal Joshi", "Person", state="Karnataka",
                notes="Brother of Pralhad Joshi, named in a cheating and ticket-promise case in 2024.")

    # 2. Relationships
    rel(c, joshi, jyoti, "Family_Link", "Spouse declared in affidavits", WIKI_URL)
    rel(c, joshi, gopal, "Family_Link", "Brother relationship mentioned in public records", NDTV_URL)

    # 3. Declarations
    decl(c, joshi, 2014, 7.8 * CR, 1.5 * CR, 18 * L, ECI_2014)
    decl(c, joshi, 2019, 11.2 * CR, 2.4 * CR, 45 * L, ECI_2019)
    decl(c, joshi, 2024, 21.1 * CR, 8.0 * CR, 2.2 * CR, ECI_2024)

    # 4. Tenures
    tenure(c, joshi, "Member of Parliament (Dharwad)", "2004-05-17", source=WIKI_URL)
    tenure(c, joshi, "Minister of Coal and Mines", "2019-05-30", "2024-06-09", source=WIKI_URL)
    tenure(c, joshi, "Minister of New and Renewable Energy", "2024-06-10", source=WIKI_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Pralhad Joshi case study data!")


if __name__ == "__main__":
    main()
