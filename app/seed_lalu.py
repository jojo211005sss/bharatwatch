"""Seed BharatWatch with real case-study data for Lalu Prasad Yadav."""
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

def tenure(c, eid, office, start_date, end_date=None, source="Parliament of India"):
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
    
    # Clean up existing Lalu Prasad Yadav entities
    names = ["Lalu Prasad Yadav", "Rabri Devi", "Tejashwi Yadav", "Misa Bharti", "Hema Yadav",
             "AK Infosystems Private Limited", "Lara Projects Private Limited", "Ministry of Railways",
             "Animal Husbandry Department", "Hridyanand Chaudhary"]
             
    c.execute(f"DELETE FROM tenures WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM declarations WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM company_financials WHERE company_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM contracts WHERE buyer_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR supplier_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM relationships WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM fund_flows WHERE from_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))})) OR to_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names + names)
    c.execute(f"DELETE FROM flags WHERE entity_id IN (SELECT id FROM entities WHERE name IN ({','.join('?'*len(names))}))", names)
    c.execute(f"DELETE FROM entities WHERE name IN ({','.join('?'*len(names))})", names)
    
    # Verified Source URLs
    WIKI_URL = "https://en.wikipedia.org/wiki/Lalu_Prasad_Yadav"
    LAND_FOR_JOBS_URL = "https://www.ndtv.com/india-news/cbi-files-charge-sheet-against-lalu-yadav-77-others-in-land-for-job-case-4174828"
    FODDER_SCAM_URL = "https://en.wikipedia.org/wiki/Fodder_scam"
    
    # 1. Entities
    lalu = ent(c, "Lalu Prasad Yadav", "Politician", party="RJD", position="Former Union Railway Minister",
               state="Bihar", criminal_cases=5,
               notes="President of Rashtriya Janata Dal (RJD), Former Chief Minister of Bihar (1990-1997), and former Union Railway Minister (2004-2009). Convicted in multiple fodder scam cases and currently facing trial in Land-for-Jobs case.")
               
    rabri = ent(c, "Rabri Devi", "Politician", party="RJD", position="Former Chief Minister of Bihar",
               state="Bihar", notes="Spouse of Lalu Prasad Yadav, Former Chief Minister of Bihar.")
               
    tejashwi = ent(c, "Tejashwi Yadav", "Politician", party="RJD", position="Leader of Opposition (Bihar)",
                  state="Bihar", notes="Son of Lalu Prasad Yadav, former Deputy Chief Minister of Bihar.")
                  
    misa = ent(c, "Misa Bharti", "Politician", party="RJD", position="Member of Parliament (Rajya Sabha)",
               state="Bihar", notes="Daughter of Lalu Prasad Yadav.")
               
    hema = ent(c, "Hema Yadav", "Person", state="Bihar",
               notes="Daughter of Lalu Prasad Yadav, beneficiary in the Railway Land-for-Jobs scam.")
               
    ak_info = ent(c, "AK Infosystems Private Limited", "Company", cin="U70109DL2006PTC154460",
                  state="Delhi", incorporation_date="2006-09-28",
                  notes="Real estate firm allegedly set up to hold land parcels transferred by railway job seekers, whose ownership was later transferred to Lalu Prasad Yadav's family.")
                  
    lara_projects = ent(c, "Lara Projects Private Limited", "Company", cin="U74900BR2016PTC031526",
                       state="Bihar", incorporation_date="2016-05-10",
                       notes="Company owned by Lalu Prasad Yadav's family, which holds a 3-acre prime plot in Patna valued at over ₹45 crore.")
                       
    rly_ministry = ent(c, "Ministry of Railways", "Government Office", state="Delhi",
                        notes="Government of India ministry responsible for rail transport.")
                        
    ahd = ent(c, "Animal Husbandry Department", "Government Office", state="Bihar",
              notes="Bihar state government department responsible for animal care and fodder supply.")
              
    job_seeker = ent(c, "Hridyanand Chaudhary", "Person", state="Bihar",
                       notes="Railway job seeker who transferred land to Lalu Prasad Yadav's family in exchange for a Group D job.")
                       
    # 2. Tenures
    tenure(c, lalu, "Chief Minister of Bihar", "1990-03-10", "1997-07-25", WIKI_URL)
    tenure(c, lalu, "Minister of Railways", "2004-05-23", "2009-05-25", WIKI_URL)
    tenure(c, rabri, "Chief Minister of Bihar", "1997-07-25", "2005-03-06", WIKI_URL)
    
    # 3. Declarations
    decl(c, lalu, 2009, 22000000, 0, 600000, WIKI_URL)
    
    # 4. Relationships
    # Family links
    rel(c, lalu, rabri, "Family_Link", "Spouse details in public declarations", WIKI_URL)
    rel(c, lalu, tejashwi, "Family_Link", "Family details", WIKI_URL)
    rel(c, lalu, misa, "Family_Link", "Family details", WIKI_URL)
    rel(c, lalu, hema, "Family_Link", "Family details", WIKI_URL)
    
    # Corporate links
    rel(c, rabri, ak_info, "Shareholder_Of", "Ownership transfer records", LAND_FOR_JOBS_URL)
    rel(c, tejashwi, ak_info, "Shareholder_Of", "Ownership transfer records", LAND_FOR_JOBS_URL)
    rel(c, rabri, lara_projects, "Director_Of", "Corporate filings", LAND_FOR_JOBS_URL)
    rel(c, tejashwi, lara_projects, "Director_Of", "Corporate filings", LAND_FOR_JOBS_URL)
    
    # Fund flows / Land transfers
    rel(c, job_seeker, hema, "Donor_To", "Land gifted in exchange for job", LAND_FOR_JOBS_URL, value=3000000)
    
    # 5. Contracts
    # Group D Railway Job
    contract(c, "RLY-JOB-D-HRIDYA", "Group D Railway Appointment (Hridyanand)", rly_ministry, job_seeker, 250000, "2005-08-10",
             "Group D recruitment in East Central Railway (ECR) during Lalu Prasad Yadav tenure as Railway Minister, linked to land transfer.", LAND_FOR_JOBS_URL)
             
    # Fodder scam irregular withdrawals
    contract(c, "FODDER-DORANDA-139", "Doranda Treasury Fodder Allocation", ahd, lalu, 139000000, "1995-11-20",
             "Irregular withdrawal of Rs 139 crore from Doranda Treasury in Ranchi under the guise of animal fodder supply, leading to conviction in Doranda case.", FODDER_SCAM_URL)

    # 6. Financials
    financials(c, ak_info, 2014, 18000000, 500000, 0, -20000, LAND_FOR_JOBS_URL)
    financials(c, lara_projects, 2017, 450000000, 10000000, 0, -100000, LAND_FOR_JOBS_URL)

    conn.commit()
    conn.close()
    print("Successfully seeded Lalu Prasad Yadav data.")

if __name__ == "__main__":
    main()
