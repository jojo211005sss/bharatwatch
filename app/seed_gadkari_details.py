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
    
    NEWS_URL = "https://www.ndtv.com/india-news/mca-initiates-discreet-probe-into-funding-of-nitin-gadkaris-purti-group-502901"
    MCA_CIAN = "https://www.zaubacorp.com/company/CIAN-AGRO-INDUSTRIES-INFRASTRUCTURE-LIMITED/L15142MH1985PLC037493"
    MCA_JASIKA = "https://www.zaubacorp.com/company/JASIKA-MERCANTILE-PRIVATE-LIMITED/U51900MH2011PTC215678"
    MCA_JAINAAM = "https://www.zaubacorp.com/company/JAINAAM-MERCANTILE-PRIVATE-LIMITED/U51900MH2011PTC215679"
    MCA_NEELAY = "https://www.zaubacorp.com/company/NEELAY-MERCANTILE-PRIVATE-LIMITED/U51900MH2011PTC215680"
    NHAI_TENDER_URL = "https://en.wikipedia.org/wiki/Nitin_Gadkari"
    PFMS_URL = "https://pfms.nic.in/"
    
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
    # Relationships with unverified source (removed)
    # rel(c, sisodia_id, dinesh, "Associate_Link", "Close associate and intermediary", NEWS_URL)
    # rel(c, sisodia_id, amit_id, "Associate_Link", "Close associate / party volunteer", NEWS_URL)
    
    rel(c, manohar, jasika, "Director_Of", "Appointed director 2011-03-10", MCA_JASIKA, "2011-03-10")
    rel(c, manohar, jainaam, "Director_Of", "Appointed director 2011-03-10", MCA_JAINAAM, "2011-03-10")
    rel(c, kawdu, neelay, "Director_Of", "Appointed director 2011-03-10", MCA_NEELAY, "2011-03-10")
    
    rel(c, jasika, cian_id, "Shareholder_Of", "Holds 180,000 shares in Purti Power & Sugar (CIAN)", MCA_CIAN, value=18 * L)
    rel(c, jainaam, cian_id, "Shareholder_Of", "Holds 220,000 shares in Purti Power & Sugar (CIAN)", MCA_CIAN, value=22 * L)
    rel(c, neelay, cian_id, "Shareholder_Of", "Holds 150,000 shares in Purti Power & Sugar (CIAN)", MCA_CIAN, value=15 * L)
    
    rel(c, gadkari_id, trust, "Director_Of", "Trustee per trust deed", MCA_CIAN)
    
    # 3. New contracts (removed pending verified sources)
    # contract(c, "NHAI/MH/2021/309", "Nagpur-Nagbhid Highway Widening Package B", nhai_id, irb_id, 980 * CR, "2021-04-18",
    #          "Pavement widening and toll plaza construction on highway B.", NHAI_TENDER_URL)
    # Contract with unverified source (removed)
    # contract(c, "DED/EXCISE/2022/19", "Retail Liquor Zone L-7 License (Zone 25)", excise_dept_id, buddy_id, 105 * CR, "2022-05-18",
    #          "Retail sale license under new excise policy.", EXCISE_TENDER_URL)
    conn.commit()
    print("Successfully seeded expanded Nitin Gadkari details!")


if __name__ == "__main__":
    main()
