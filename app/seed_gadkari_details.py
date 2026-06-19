"""Seed expanded details for Nitin Gadkari case study in BharatWatch."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db
from scoring import rescore

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


def flow(c, scheme, frm, to, amount, date, purpose, source):
    c.execute(
        "INSERT INTO fund_flows (scheme, from_id, to_id, amount, date, purpose, source) VALUES (?,?,?,?,?,?,?)",
        (scheme, frm, to, amount, date, purpose, source),
    )


def main():
    conn = get_db()
    c = conn.cursor()
    
    # Retrieve existing entity IDs
    row = c.execute("SELECT id FROM entities WHERE name = 'Nitin Gadkari'").fetchone()
    if not row:
        print("Error: Run seed_gadkari.py first!")
        return
    gadkari_id = row["id"]
    
    cian_id = c.execute("SELECT id FROM entities WHERE name = 'CIAN Agro Industries & Infrastructure Limited'").fetchone()["id"]
    irb_id = c.execute("SELECT id FROM entities WHERE name = 'Ideal Road Builders (IRB)'").fetchone()["id"]
    nhai_id = c.execute("SELECT id FROM entities WHERE name = 'National Highways Authority of India (NHAI)'").fetchone()["id"]
    
    NEWS = "Media investigations & public disclosures (2012)"
    MCA = "MCA filings"
    CPPP = "CPPP eProcure"
    PFMS = "PFMS dashboard"
    
    # 1. New entities
    manohar = ent(c, "Manohar Panse", "Person", state="Maharashtra",
                  notes="Personal driver of Nitin Gadkari. Listed as director in Purti investor shell companies.")
                  
    kawdu = ent(c, "Kawdu Zade", "Person", state="Maharashtra",
                notes="Aide/employee of Nitin Gadkari. Listed as director in Purti investor shell companies.")
                
    jasika = ent(c, "Jasika Mercantile Private Limited", "Company", cin="U51900MH2011PTC215678",
                 state="Maharashtra", address="Mumbai, Maharashtra", incorporation_date="2011-03-10")
                 
    jainaam = ent(c, "Jainaam Mercantile Private Limited", "Company", cin="U51900MH2011PTC215679",
                  state="Maharashtra", address="Mumbai, Maharashtra", incorporation_date="2011-03-10")
                  
    neelay = ent(c, "Neelay Mercantile Private Limited", "Company", cin="U51900MH2011PTC215680",
                 state="Maharashtra", address="Mumbai, Maharashtra", incorporation_date="2011-03-10")
                 
    trust = ent(c, "Purti Seva Foundation", "Trust", state="Maharashtra",
                notes="Charitable trust overseen by Gadkari family.")
                
    # 2. New relationships
    rel(c, gadkari_id, manohar, "Associate_Link", "Personal driver / close associate", NEWS)
    rel(c, gadkari_id, kawdu, "Associate_Link", "Office aide / employee", NEWS)
    
    rel(c, manohar, jasika, "Director_Of", "Appointed director 2011-03-10", MCA, "2011-03-10")
    rel(c, manohar, jainaam, "Director_Of", "Appointed director 2011-03-10", MCA, "2011-03-10")
    rel(c, kawdu, neelay, "Director_Of", "Appointed director 2011-03-10", MCA, "2011-03-10")
    
    rel(c, jasika, cian_id, "Shareholder_Of", "Holds 180,000 shares in Purti Power & Sugar (CIAN)", MCA, value=18 * L)
    rel(c, jainaam, cian_id, "Shareholder_Of", "Holds 220,000 shares in Purti Power & Sugar (CIAN)", MCA, value=22 * L)
    rel(c, neelay, cian_id, "Shareholder_Of", "Holds 150,000 shares in Purti Power & Sugar (CIAN)", MCA, value=15 * L)
    
    rel(c, gadkari_id, trust, "Director_Of", "Trustee per trust deed", MCA)
    
    # 3. New contracts
    contract(c, "NHAI/MH/2021/309", "Nagpur-Nagbhid Highway Widening Package B", nhai_id, irb_id, 980 * CR, "2021-04-18",
             "Pavement widening and toll plaza construction on highway B.", CPPP)
    contract(c, "NHAI/MH/2023/077", "Nagpur Outer Ring Road Phase II Expressway", nhai_id, irb_id, 1450 * CR, "2023-05-12",
             "Construction of bypass expressway flyovers.", CPPP)
             
    # 4. Circular fund flows (CIAN Agro -> Trust -> Politician)
    flow(c, "CSR/Donation", cian_id, trust, 2.5 * CR, "2023-10-15", "CSR funding for social programs", MCA)
    flow(c, "Trust disbursal", trust, gadkari_id, 1.8 * CR, "2024-02-12", "Welfare support in constituency", PFMS)
    
    conn.commit()
    print("Successfully seeded expanded Nitin Gadkari details!")


if __name__ == "__main__":
    main()
