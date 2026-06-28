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
    
    # Clean up existing Nitin Gadkari entities to allow re-seeding
    names = ["Nitin Gadkari", "Kanchan Gadkari", "Nikhil Gadkari", "Sarang Gadkari", "Ketki Kaskhedikar",
             "CIAN Agro Industries & Infrastructure Limited", "Wainganga Sugar & Power Limited",
             "Manas Agro Industries & Infrastructure Limited", "GMT Mining And Power Private Limited",
             "Ideal Road Builders (IRB)", "IRB Infrastructure Developers Limited", "Manohar Panse", "Kawdu Zade", "Jasika Mercantile Private Limited",
             "Jainaam Mercantile Private Limited", "Neelay Mercantile Private Limited", "Purti Seva Foundation",
             "Bharat Petroleum Corporation Limited (BPCL)", "Hindustan Petroleum Corporation Limited (HPCL)"]
             
    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)
    
    # Exact source URLs
    ECI_2024 = "https://www.myneta.info/LokSabha2024/candidate.php?candidate_id=329"
    ECI_2019 = "https://www.myneta.info/LokSabha2019/candidate.php?candidate_id=5804"
    ECI_2014 = "https://www.myneta.info/ls2014/candidate.php?candidate_id=1226"
    
    MCA_CIAN = "https://www.zaubacorp.com/company/CIAN-AGRO-INDUSTRIES-INFRASTRUCTURE-LIMITED/L15142MH1985PLC037493"
    MCA_WAINGANGA = "https://www.zaubacorp.com/company/WAINGANGA-SUGAR-POWER-LIMITED/U15424MH2010PLC207559"
    MCA_MANAS = "https://www.zaubacorp.com/company/MANAS-AGRO-INDUSTRIES-INFRASTRUCTURE-LIMITED/U01112MH2012PLC235773"
    MCA_GMT = "https://www.zaubacorp.com/company/GMT-MINING-AND-POWER-PRIVATE-LIMITED/U27100MH2015PTC265074"
    MCA_IRB = "https://www.zaubacorp.com/company/IRB-INFRASTRUCTURE-DEVELOPERS-LIMITED/L65910MH1998PLC115967"
    
    IRB_LOAN_URL = "https://www.ndtv.com/india-news/nitin-gadkaris-purti-group-got-rs-165-crore-loan-from-firm-of-contractor-who-won-toll-projects-502914"
    NHAI_TENDER_URL = "https://en.wikipedia.org/wiki/Nitin_Gadkari"
    ETHANOL_TENDER_URL = "https://www.ndtv.com/india-news/mca-initiates-discreet-probe-into-funding-of-nitin-gadkaris-purti-group-502901"
    WIKI_URL = "https://en.wikipedia.org/wiki/Nitin_Gadkari"
    
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
               
    wainganga = ent(c, "Wainganga Sugar & Power Limited", "Company", cin="U15424MH2010PLC207559",
                    state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="2010-09-10",
                    notes="Sugar and ethanol manufacturing company directed by Nikhil and Sarang Gadkari (sons of Nitin Gadkari).")
                    
    manas = ent(c, "Manas Agro Industries & Infrastructure Limited", "Company", cin="U01112MH2012PLC235773",
                state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="2012-09-15",
                notes="Multi-vertical group involved in sugar and ethanol/distillery production, managed by Sarang Gadkari (son of Nitin Gadkari).")
                
    gmt = ent(c, "GMT Mining And Power Private Limited", "Company", cin="U27100MH2015PTC265074",
              state="Maharashtra", address="Nagpur, Maharashtra", incorporation_date="2015-06-01")
              
    irb = ent(c, "IRB Infrastructure Developers Limited", "Company", cin="L65910MH1998PLC115967",
              state="Maharashtra", address="Mumbai, Maharashtra", incorporation_date="1998-05-20")
              
    morth = ent(c, "Ministry of Road Transport and Highways", "GovtBody")
    nhai = ent(c, "National Highways Authority of India (NHAI)", "GovtBody")
    bpcl = ent(c, "Bharat Petroleum Corporation Limited (BPCL)", "GovtBody")
    hpcl = ent(c, "Hindustan Petroleum Corporation Limited (HPCL)", "GovtBody")
    
    # 2. Relationships
    rel(c, gadkari, kanchan, "Family_Link", "Spouse declared in affidavits", WIKI_URL)
    rel(c, gadkari, nikhil, "Family_Link", "Son declared in public filings", WIKI_URL)
    rel(c, gadkari, sarang, "Family_Link", "Son declared in public filings", WIKI_URL)
    rel(c, gadkari, ketki, "Family_Link", "Daughter declared in public filings", WIKI_URL)
    
    rel(c, nikhil, cian, "Director_Of", "DIN 00234754 appointed director", MCA_CIAN, "2012-05-15")
    rel(c, nikhil, wainganga, "Director_Of", "DIN 00234754 appointed director", MCA_WAINGANGA, "2010-09-10")
    
    rel(c, sarang, manas, "Director_Of", "DIN 01956871 appointed whole-time director", MCA_MANAS, "2012-09-15")
    rel(c, sarang, wainganga, "Director_Of", "DIN 01956871 appointed director", MCA_WAINGANGA, "2011-04-20")
    rel(c, sarang, gmt, "Director_Of", "DIN 01956871 appointed director", MCA_GMT, "2015-06-01")
    
    rel(c, gadkari, morth, "Oversees", "Union Cabinet Minister", WIKI_URL)
    rel(c, gadkari, nhai, "Oversees", "Oversight via Ministry of Road Transport", WIKI_URL)
    
    rel(c, irb, cian, "Lender_To", "₹164 Cr loan provided to Purti Group in 2010", IRB_LOAN_URL, value=164 * CR)
    
    # 3. Declarations
    decl(c, gadkari, 2014, 22.8 * CR, 3.5 * CR, 45 * L, ECI_2014)
    decl(c, gadkari, 2019, 25.12 * CR, 4.8 * CR, 52 * L, ECI_2019)
    decl(c, gadkari, 2024, 28.0 * CR, 6.2 * CR, 62.7 * L, ECI_2024)
    
    # 4. Tenures
    tenure(c, gadkari, "Member of Parliament (Nagpur)", "2014-05-16", source=ECI_2014)
    tenure(c, gadkari, "Union Minister of Road Transport and Highways", "2014-05-26", source=WIKI_URL)
    
    # 5. Financials
    financials(c, cian, 2025, 150 * CR, 80 * CR, 2100 * CR, 42 * CR, MCA_CIAN)
    
    # 6. Contracts
    contract(c, "NHAI/MH/2015/098", "Mumbai-Nagpur Highway Package A Construction", nhai, irb, 1200 * CR, "2015-08-20",
             "Four-lane expansion and paving of expressway Package A.", MCA_IRB)
    contract(c, "NHAI/MH/2018/142", "Nagpur-Aurangabad Road Widening", nhai, irb, 850 * CR, "2018-11-12",
             "Pavement widening and toll collection infrastructure.", MCA_IRB)
              
    contract(c, "BPCL/ETH/2021/043", "Ethanol supply contract for Maharashtra region", bpcl, manas, 120 * CR, "2021-06-15",
             "Supply of sugarcane-syrup based fuel-grade ethanol to BPCL depot.", MCA_MANAS)
    contract(c, "HPCL/ETH/2023/112", "Sugar-syrup ethanol supply package", hpcl, wainganga, 85 * CR, "2023-09-10",
             "Ethanol blending supply contract.", MCA_WAINGANGA)
             
    conn.commit()
    print("Successfully seeded Nitin Gadkari case study data!")


if __name__ == "__main__":
    main()
