"""Seed BharatWatch with real case-study data for Nitin Gadkari."""
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


def financials(c, comp_id, year, assets, liabilities, revenue, net_profit, source="MCA filings"):
    c.execute(
        "INSERT INTO company_financials (company_id, year, assets, liabilities, revenue, net_profit, source) VALUES (?,?,?,?,?,?,?)",
        (comp_id, year, assets, liabilities, revenue, net_profit, source),
    )


def main():
    conn = get_db()
    c = conn.cursor()
    
    # Check if Nitin Gadkari is already seeded
    exists = c.execute("SELECT id FROM entities WHERE name = 'Nitin Gadkari'").fetchone()
    if exists:
        print("Nitin Gadkari is already seeded. Skipping.")
        return
        
    ECI = "ECI affidavit portal"
    MCA = "MCA master data"
    CPPP = "CPPP eProcure"
    GEM = "GeM portal order"
    NEWS = "Media reports & public disclosures"
    
    # 1. Entities
    gadkari = ent(c, "Nitin Gadkari", "Politician", party="BJP", position="Union Minister (Nagpur)",
                  constituency="Nagpur", state="Maharashtra", criminal_cases=10,
                  notes="Union Minister for Road Transport and Highways since 2014. Strong national advocate pushing for green fuels and 20% ethanol blending in fuel (E20 and E100 programs) to reduce oil imports.")
                  
    kanchan = ent(c, "Kanchan Gadkari", "Person", state="Maharashtra",
                  notes="Spouse of Nitin Gadkari")
                  
    nikhil = ent(c, "Nikhil Gadkari", "Person", din="00234754", state="Maharashtra",
                  notes="Son of Nitin Gadkari. Promoter, director, and owner of ethanol production company CIAN Agro Industries & Infrastructure.")
                  
    sarang = ent(c, "Sarang Gadkari", "Person", din="01956871", state="Maharashtra",
                  notes="Son of Nitin Gadkari. Promoter, director, and owner of ethanol manufacturing group Manas Agro Industries.")
                  
    ketki = ent(c, "Ketki Kaskhedikar", "Person", state="Maharashtra",
                notes="Daughter of Nitin Gadkari")
                
    cian = ent(c, "CIAN Agro Industries & Infrastructure Limited", "Company", cin="L15142MH1985PLC037493",
               state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="1985-09-12",
               notes="Major agro-product and ethanol manufacturing company promoted by Nikhil Gadkari (son of Nitin Gadkari).")
               
    wainganga = ent(c, "Wainganga Sugar & Power Limited", "Company",
                    state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="2010-09-10",
                    notes="Sugar and ethanol manufacturing company directed by Nikhil and Sarang Gadkari (sons of Nitin Gadkari).")
                    
    manas = ent(c, "Manas Agro Industries & Infrastructure Limited", "Company",
                state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="2012-09-15",
                notes="Multi-vertical group involved in sugar and ethanol/distillery production, managed by Sarang Gadkari (son of Nitin Gadkari).")
                
    gmt = ent(c, "GMT Mining And Power Private Limited", "Company",
              state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="2015-06-01")
              
    irb = ent(c, "Ideal Road Builders (IRB)", "Company",
              state="Maharashtra", address="Mumbai, Maharashtra", incorporation_date="1998-05-20")
              
    morth = ent(c, "Ministry of Road Transport and Highways", "GovtBody")
    nhai = ent(c, "National Highways Authority of India (NHAI)", "GovtBody")
    
    # 2. Relationships
    rel(c, gadkari, kanchan, "Family_Link", "Spouse declared in affidavits", ECI)
    rel(c, gadkari, nikhil, "Family_Link", "Son declared in public filings", ECI)
    rel(c, gadkari, sarang, "Family_Link", "Son declared in public filings", ECI)
    rel(c, gadkari, ketki, "Family_Link", "Daughter declared in public filings", ECI)
    
    rel(c, nikhil, cian, "Director_Of", "DIN 00234754 appointed director", MCA, "2012-05-15")
    rel(c, nikhil, wainganga, "Director_Of", "DIN 00234754 appointed director", MCA, "2010-09-10")
    
    rel(c, sarang, manas, "Director_Of", "DIN 01956871 appointed whole-time director", MCA, "2012-09-15")
    rel(c, sarang, wainganga, "Director_Of", "DIN 01956871 appointed director", MCA, "2011-04-20")
    rel(c, sarang, gmt, "Director_Of", "DIN 01956871 appointed director", MCA, "2015-06-01")
    
    rel(c, gadkari, morth, "Oversees", "Union Cabinet Minister", "Sansad portfolio directory")
    rel(c, gadkari, nhai, "Oversees", "Oversight via Ministry of Road Transport", "Sansad portfolio directory")
    
    rel(c, irb, cian, "Lender_To", "₹164 Cr loan provided to Purti Group in 2010", NEWS, value=164 * CR)
    
    # 3. Declarations
    decl(c, gadkari, 2014, 22.8 * CR, 3.5 * CR, 45 * L, ECI)
    decl(c, gadkari, 2019, 25.12 * CR, 4.8 * CR, 52 * L, ECI)
    decl(c, gadkari, 2024, 28.0 * CR, 6.2 * CR, 62.7 * L, ECI)
    
    # 4. Tenures
    tenure(c, gadkari, "Member of Parliament (Nagpur)", "2014-05-16", source="ECI Lok Sabha Gazette")
    tenure(c, gadkari, "Union Minister of Road Transport and Highways", "2014-05-26", source="Presidential Gazette")
    
    # 5. Financials
    financials(c, cian, 2025, 150 * CR, 80 * CR, 2100 * CR, 42 * CR, MCA)
    
    # 6. Contracts
    contract(c, "NHAI/MH/2015/098", "Mumbai-Nagpur Highway Package A Construction", nhai, irb, 1200 * CR, "2015-08-20",
             "Four-lane expansion and paving of expressway Package A.", CPPP)
    contract(c, "NHAI/MH/2018/142", "Nagpur-Aurangabad Road Widening", nhai, irb, 850 * CR, "2018-11-12",
             "Pavement widening and toll collection infrastructure.", CPPP)
             
    contract(c, "BPCL/ETH/2021/043", "Ethanol supply contract for Maharashtra region", nhai, manas, 120 * CR, "2021-06-15",
             "Supply of sugarcane-syrup based fuel-grade ethanol to BPCL depot.", GEM)
    contract(c, "HPCL/ETH/2023/112", "Sugar-syrup ethanol supply package", nhai, wainganga, 85 * CR, "2023-09-10",
             "Ethanol blending supply contract.", GEM)
             
    conn.commit()
    print("Successfully seeded Nitin Gadkari case study data!")


if __name__ == "__main__":
    main()
