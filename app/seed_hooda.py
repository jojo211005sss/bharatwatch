"""Seed BharatWatch with real case-study data for Bhupinder Singh Hooda."""
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

    # Clean up existing Bhupinder Singh Hooda entities to allow re-seeding
    names = ["Bhupinder Singh Hooda", "Asha Hooda", "Deepender Singh Hooda",
             "ABW Infrastructure Limited", "Directorate of Town and Country Planning (DTCP) Haryana"]

    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)

    # Exact source URLs
    ECI_2024 = "https://www.myneta.info/Haryana2024/candidate.php?candidate_id=254"
    ECI_2019 = "https://www.myneta.info/haryana2019/candidate.php?candidate_id=8055"
    ECI_2014 = "https://www.myneta.info/haryana2014/candidate.php?candidate_id=596"

    WIKI_URL = "https://en.wikipedia.org/wiki/Bhupinder_Singh_Hooda"
    NDTV_URL = "https://www.ndtv.com/india-news/cbi-files-chargesheet-against-bhupinder-singh-hooda-in-manesar-land-scam-case-1807758"

    # 1. Entities
    hooda = ent(c, "Bhupinder Singh Hooda", "Politician", party="INC", position="Leader of Opposition (Haryana)",
                constituency="Garhi Sampla-Kiloi", state="Haryana", criminal_cases=4,
                notes="Former Chief Minister of Haryana (2005-2014). Named in CBI chargesheets regarding irregular land acquisitions and license awards in Manesar.")

    asha = ent(c, "Asha Hooda", "Person", state="Haryana",
              notes="Spouse of Bhupinder Singh Hooda")

    deepender = ent(c, "Deepender Singh Hooda", "Politician", party="INC", position="Member of Parliament (Rohtak)",
                      state="Haryana", notes="Son of Bhupinder Singh Hooda, MP Lok Sabha representing Rohtak.")

    abw = ent(c, "ABW Infrastructure Limited", "Company", cin="U45200DL2002PLC117855",
              state="Delhi", address="Connaught Place, New Delhi", incorporation_date="2002-11-20",
              notes="Real estate development company named as co-accused in the Manesar land acquisition scam chargesheet.")

    dtcp = ent(c, "Directorate of Town and Country Planning (DTCP) Haryana", "GovtBody", state="Haryana",
                notes="Haryana state government regulatory body responsible for urban planning and builder licensing.")

    # 2. Relationships
    rel(c, hooda, asha, "Family_Link", "Spouse declared in affidavits", WIKI_URL)
    rel(c, hooda, deepender, "Family_Link", "Son declared in public listings", WIKI_URL)
    rel(c, hooda, dtcp, "Oversees", "Chief Minister of Haryana with ministerial control", NDTV_URL)

    # 3. Declarations
    decl(c, hooda, 2014, 8.4 * CR, 1.2 * CR, 24 * L, ECI_2014)
    decl(c, hooda, 2019, 15.6 * CR, 2.1 * CR, 38 * L, ECI_2019)
    decl(c, hooda, 2024, 26.4 * CR, 3.5 * CR, 55 * L, ECI_2024)

    # 4. Tenures
    tenure(c, hooda, "Chief Minister of Haryana", "2005-03-05", "2014-10-26", source=WIKI_URL)
    tenure(c, hooda, "MLA from Garhi Sampla-Kiloi", "2005-05-10", source=WIKI_URL)
    tenure(c, deepender, "Member of Parliament (Rohtak)", "2009-05-18", source=WIKI_URL)

    # 5. Contracts
    contract(c, "MANESAR-LAND-LIC-ABW", "Manesar Group Housing License Award", dtcp, abw, 1500 * CR, "2007-08-10",
             "Release of 400 acres land in Manesar and grant of residential group housing license to ABW Infrastructure.", NDTV_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Bhupinder Singh Hooda case study data!")


if __name__ == "__main__":
    main()
