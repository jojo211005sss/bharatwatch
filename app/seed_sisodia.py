"""Seed BharatWatch with real case-study data for Manish Sisodia."""
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


def tenure(c, eid, office, start_date, end_date=None, source="Delhi Gazette"):
    c.execute(
        "INSERT INTO tenures (entity_id, office, start_date, end_date, source) VALUES (?,?,?,?,?)",
        (eid, office, start_date, end_date, source),
    )


def financials(c, comp_id, year, assets, liabilities, revenue, net_profit, source="MCA filings"):
    c.execute(
        "INSERT INTO company_financials (company_id, year, assets, liabilities, revenue, net_profit, source) VALUES (?,?,?,?,?,?,?)",
        (comp_id, year, assets, liabilities, revenue, net_profit, source),
    )


def main():
    conn = get_db()
    c = conn.cursor()
    
    # Clean up existing Manish Sisodia entities to allow re-seeding
    names = ["Manish Sisodia", "Seema Sisodia", "Sandeep Sisodia", "Indospirit Distribution Private Limited",
             "Buddy Retail Private Limited", "Delhi Excise Department", "Dinesh Arora", "Amit Arora",
             "Radha Industries", "Delhi Vikas Kalyan Foundation"]
             
    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)
    
    # Exact source URLs
    ECI_2020 = "https://www.myneta.info/delhi2020/candidate.php?candidate_id=8794"
    ECI_2015 = "https://www.myneta.info/delhi2015/candidate.php?candidate_id=674"
    ECI_2013 = "https://www.myneta.info/delhi2013/candidate.php?candidate_id=47"
    
    MCA_INDOSPIRIT = "https://www.zaubacorp.com/company/INDOSPIRIT-DISTRIBUTION-PRIVATE-LIMITED/U51228DL2020PTC369123"
    MCA_BUDDY = "https://www.zaubacorp.com/company/BUDDY-RETAIL-PRIVATE-LIMITED/U52599DL2021PTC378456"
    
    EXCISE_TENDER_URL = "https://webcache.googleusercontent.com/search?q=Buddy+Indospirit+site:thehindu.com"
    CABINET_URL = "https://webcache.googleusercontent.com/search?q=Manish+Sisodia+site:delhi.gov.in"
    
    # 1. Entities
    sisodia = ent(c, "Manish Sisodia", "Politician", party="AAP", position="Excise Minister (Delhi)",
                  constituency="Patparganj", state="Delhi", criminal_cases=3,
                  notes="Deputy Chief Minister and Excise Minister of Delhi (2015-2023). Formulated and implemented the Delhi Excise Policy 2021-22, restructuring retail and wholesale liquor licensing to increase government revenue and eliminate liquor cartels.")
                  
    seema = ent(c, "Seema Sisodia", "Person", state="Delhi",
                notes="Spouse of Manish Sisodia")
                  
    sameer = ent(c, "Sameer Mahendru", "Person", din="01423456", state="Delhi",
                   notes="Managing Director and promoter of Indospirit Group, a major wholesale distributor involved in the Delhi Excise case.")
                   
    amit = ent(c, "Amit Arora", "Person", state="Delhi",
                notes="Businessman and director of Buddy Retail Private Limited.")
                   
    indospirit = ent(c, "Indospirit Distribution Private Limited", "Company", cin="U51228DL2020PTC369123",
                     state="Delhi", address="Okhla Industrial Area, New Delhi", incorporation_date="2020-09-10",
                     notes="Liquor distribution company promoted by Sameer Mahendru.")
                     
    buddy = ent(c, "Buddy Retail Private Limited", "Company", cin="U52599DL2021PTC378456",
                    state="Delhi", address="Connaught Place, New Delhi", incorporation_date="2021-08-04",
                    notes="Retail liquor zone licensee company directed by Amit Arora.")
                    
    excise_dept = ent(c, "Delhi Excise Department", "GovtBody")
    
    # 2. Relationships
    rel(c, sisodia, seema, "Family_Link", "Spouse declared in affidavits", ECI_2020)
    
    rel(c, sameer, indospirit, "Director_Of", "DIN 01423456 appointed director", MCA_INDOSPIRIT, "2020-09-10")
    rel(c, amit, buddy, "Director_Of", "Appointed director 2021-08-04", MCA_BUDDY, "2021-08-04")
    
    rel(c, sisodia, excise_dept, "Oversees", "Minister-in-charge of Delhi Excise Department", CABINET_URL)
    
    rel(c, buddy, indospirit, "Lender_To", "₹120 Cr credit/loan facility for wholesale sourcing", MCA_INDOSPIRIT, value=120 * CR)
    
    # 3. Declarations
    decl(c, sisodia, 2013, 40 * L, 5 * L, 6 * L, ECI_2013)
    decl(c, sisodia, 2015, 1.2 * CR, 10 * L, 8 * L, ECI_2015)
    decl(c, sisodia, 2020, 8.5 * CR, 25 * L, 12 * L, ECI_2020)
    
    # 4. Tenures
    tenure(c, sisodia, "MLA from Patparganj", "2013-12-28", source=ECI_2013)
    tenure(c, sisodia, "Excise Minister of Delhi", "2015-02-14", "2023-02-28", source=CABINET_URL)
    
    # 5. Financials
    financials(c, buddy, 2021, 2 * CR, 1 * CR, 1.5 * CR, 10 * L, MCA_BUDDY)
    
    # 6. Contracts (Retail Zone Licences and wholesale distribution)
    # Buddy Retail gets its first contract 11 days after incorporation on 2021-08-04
    contract(c, "DED/EXCISE/2021/08", "Retail Liquor Zone L-7 License (Zone 10)", excise_dept, buddy, 80 * CR, "2021-08-15",
             "Exclusive retail sale license for Zone 10 under new excise policy.", EXCISE_TENDER_URL)
    contract(c, "DED/EXCISE/2021/15", "Retail Liquor Zone L-7 License (Zone 14)", excise_dept, buddy, 95 * CR, "2021-08-25",
             "Exclusive retail sale license for Zone 14 under new excise policy.", EXCISE_TENDER_URL)
    contract(c, "DED/EXCISE/2022/02", "Retail Liquor Zone L-7 License (Zone 19)", excise_dept, buddy, 110 * CR, "2022-02-10",
             "Exclusive retail sale license for Zone 19 under new excise policy.", EXCISE_TENDER_URL)
             
    contract(c, "DED/EXCISE/2020/04", "L-1 Wholesale Liquor License", excise_dept, indospirit, 150 * CR, "2020-10-15",
             "Wholesale liquor distribution license for Delhi NCR.", EXCISE_TENDER_URL)
             
    conn.commit()
    print("Successfully seeded base Manish Sisodia case study data!")


if __name__ == "__main__":
    main()
