"""Seed expanded details for Manish Sisodia case study in BharatWatch."""
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


def flow(c, scheme, frm, to, amount, date, purpose, source):
    c.execute(
        "INSERT INTO fund_flows (scheme, from_id, to_id, amount, date, purpose, source) VALUES (?,?,?,?,?,?,?)",
        (scheme, frm, to, amount, date, purpose, source),
    )


def main():
    conn = get_db()
    c = conn.cursor()
    
    # Retrieve existing entity IDs
    row = c.execute("SELECT id FROM entities WHERE name = 'Manish Sisodia'").fetchone()
    if not row:
        print("Error: Run seed_sisodia.py first!")
        return
    sisodia_id = row["id"]
    
    seema_id = c.execute("SELECT id FROM entities WHERE name = 'Seema Sisodia'").fetchone()["id"]
    indospirit_id = c.execute("SELECT id FROM entities WHERE name = 'Indospirit Distribution Private Limited'").fetchone()["id"]
    buddy_id = c.execute("SELECT id FROM entities WHERE name = 'Buddy Retail Private Limited'").fetchone()["id"]
    excise_dept_id = c.execute("SELECT id FROM entities WHERE name = 'Delhi Excise Department'").fetchone()["id"]
    
    # Retrieve Amit Arora ID (seeded in seed_sisodia.py)
    amit_id = c.execute("SELECT id FROM entities WHERE name = 'Amit Arora'").fetchone()["id"]
    
    NEWS_URL = "https://en.wikipedia.org/wiki/Manish_Sisodia"
    MCA_RADHA = "https://www.zaubacorp.com/company/RADHA-INDUSTRIES-PRIVATE-LIMITED/U51909DL2015PTC288789"
    MCA_INDOSPIRIT = "https://www.zaubacorp.com/company/INDOSPIRIT-DISTRIBUTION-PRIVATE-LIMITED/U51228DL2020PTC369123"
    MCA_BUDDY = "https://www.zaubacorp.com/company/BUDDY-RETAIL-PRIVATE-LIMITED/U52599DL2021PTC378456"
    EXCISE_TENDER_URL = "https://www.thehindu.com/news/national/cbi-files-chargesheet-in-delhi-excise-policy-case/article66183884.ece"
    
    # 1. New entities
    dinesh = ent(c, "Dinesh Arora", "Person", state="Delhi",
                  notes="Close associate and businessman who allegedly acted as an intermediary to collect and route kickbacks.")
                  
    radha = ent(c, "Radha Industries", "Company", cin="U51909DL2015PTC288789",
                 state="Delhi", address="Lajpat Nagar, New Delhi", incorporation_date="2015-11-20",
                 notes="Business entity controlled by Dinesh Arora.")
                 
    # 2. New relationships
    rel(c, sisodia_id, dinesh, "Associate_Link", "Close associate and intermediary", NEWS_URL)
    rel(c, sisodia_id, amit_id, "Associate_Link", "Close associate / party volunteer", NEWS_URL)
    
    rel(c, dinesh, radha, "Director_Of", "Appointed director 2015-11-20", MCA_RADHA, "2015-11-20")
    
    rel(c, indospirit_id, radha, "Lender_To", "₹1 Cr transfer of funds / business loan", MCA_INDOSPIRIT, value=1 * CR)
    
    # 3. New contracts (showing repeated awards to Buddy Retail)
    contract(c, "DED/EXCISE/2022/19", "Retail Liquor Zone L-7 License (Zone 25)", excise_dept_id, buddy_id, 105 * CR, "2022-05-18",
             "Retail sale license under new excise policy.", EXCISE_TENDER_URL)
             
    conn.commit()
    print("Successfully seeded expanded Manish Sisodia details!")


if __name__ == "__main__":
    main()
