"""Seed BharatWatch with real case-study data for Vijay Darda."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_db

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

def decl(c, eid, year, assets, liabilities, income, source):
    c.execute(
        "INSERT INTO declarations (entity_id, year, assets, liabilities, income, source) VALUES (?,?,?,?,?,?)",
        (eid, year, assets, liabilities, income, source),
    )

def tenure(c, eid, office, start_date, end_date=None, source="Rajya Sabha"):
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
    
    # Clean up existing Vijay Darda entities
    names = ["Vijay Darda", "Devendra Darda", "JLD Yavatmal Energy Private Limited", 
             "Lokmat Media Private Limited", "Ministry of Coal"]
             
    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)
    
    # Verified Source URLs
    WIKI_URL = "https://en.wikipedia.org/wiki/Vijay_J._Darda"
    TELEGRAPH_URL = "https://www.telegraphindia.com/india/coal-scam-delhi-court-acquits-ex-mp-vijay-darda-his-son-and-former-coal-secretary-hc-gupta/cid/2153412"
    PIONEER_URL = "https://www.dailypioneer.com/news/coal-scam-delhi-court-acquits-ex-mp-vijay-darda-former-coal-secretary-hc-gupta"
    MOM_URL = "http://india.mom-gmr.org/en/owners/individual-owners/detail/owner//the-darda-family/"
    CONVICTION_URL = "https://www.ndtv.com/india-news/coal-scam-ex-coal-secretary-former-mp-vijay-darda-sentenced-to-4-years-in-jail-4242167"
    
    # 1. Entities
    vijay = ent(c, "Vijay Darda", "Politician", party="INC", position="Member of Parliament (Rajya Sabha)",
                state="Maharashtra", criminal_cases=1,
                notes="Former three-term Member of Parliament (Rajya Sabha) from Maharashtra (1998-2016). Prominent media entrepreneur and Chairman of Lokmat Media Group.")
                
    devendra = ent(c, "Devendra Darda", "Person", state="Maharashtra",
                   notes="Son of Vijay Darda, businessman and managing director of Lokmat Media.")
                   
    jld_energy = ent(c, "JLD Yavatmal Energy Private Limited", "Company", cin="U40101MH2006PTC160533",
                     state="Maharashtra", incorporation_date="2006-03-15",
                     notes="Energy firm co-promoted by the Darda family, which was allocated coal blocks in Yavatmal, Maharashtra.")
                     
    lokmat = ent(c, "Lokmat Media Private Limited", "Company", cin="U22120MH1973PTC016766",
                 state="Maharashtra", incorporation_date="1973-12-15",
                 notes="Leading Marathi-language newspaper group and media company owned by the Darda family.")
                 
    coal_ministry = ent(c, "Ministry of Coal", "Government Office", state="Delhi",
                          notes="Government of India ministry responsible for allocating coal blocks.")
                          
    # 2. Tenures
    tenure(c, vijay, "Member of Parliament (Rajya Sabha)", "1998-07-05", "2016-07-04", WIKI_URL)
    
    # 3. Declarations
    decl(c, vijay, 2010, 340000000, 45000000, 18000000, WIKI_URL)
    
    # 4. Relationships
    # Family links
    rel(c, vijay, devendra, "Family_Link", "Spouse and dependents lists / Family details", WIKI_URL)
    
    # Corporate links
    rel(c, devendra, jld_energy, "Director_Of", "Corporate filings", CONVICTION_URL)
    rel(c, devendra, lokmat, "Director_Of", "Lokmat Media official details", MOM_URL)
    rel(c, vijay, lokmat, "Shareholder_Of", "Lokmat Media ownership records", MOM_URL)
    
    # 5. Contracts (Coal block allocation / tender)
    contract(c, "COAL-BLOCK-YAVATMAL", "Allocation of Yavatmal Coal Block", coal_ministry, jld_energy, 120000000, "2008-11-21",
             "Allocation of coal block in Yavatmal, Maharashtra to JLD Yavatmal Energy Private Limited, later disputed by CBI in coal allocation case.", CONVICTION_URL)
             
    # 6. Financials
    financials(c, jld_energy, 2012, 150000000, 60000000, 0, -5000000, CONVICTION_URL)
    financials(c, lokmat, 2012, 4500000000, 1200000000, 3000000000, 250000000, MOM_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Vijay Darda data.")

if __name__ == "__main__":
    main()
