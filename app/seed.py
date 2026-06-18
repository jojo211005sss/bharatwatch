"""Seed BharatWatch with FICTIONAL demonstration data.

All people, companies, contracts, and amounts below are invented to demonstrate
the detection engine. They do not refer to any real person or firm. Real data
is ingested through the admin portal from public sources (ECI, MCA, CPPP, GeM,
PFMS, data.gov.in).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import init_db

CR = 1e7  # 1 crore in rupees
L = 1e5   # 1 lakh


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


def decl(c, eid, year, assets, liabilities, income, source="ECI affidavit (demo)"):
    c.execute(
        "INSERT INTO declarations (entity_id, year, assets, liabilities, income, source) VALUES (?,?,?,?,?,?)",
        (eid, year, assets, liabilities, income, source),
    )


def tenure(c, eid, office, start_date, end_date=None, source="State Gazette (demo)"):
    c.execute(
        "INSERT INTO tenures (entity_id, office, start_date, end_date, source) VALUES (?,?,?,?,?)",
        (eid, office, start_date, end_date, source),
    )


def financials(c, comp_id, year, assets, liabilities, revenue, net_profit, source="MCA filings (demo)"):
    c.execute(
        "INSERT INTO company_financials (company_id, year, assets, liabilities, revenue, net_profit, source) VALUES (?,?,?,?,?,?,?)",
        (comp_id, year, assets, liabilities, revenue, net_profit, source),
    )


def seed():
    conn = init_db()
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    if n:
        print(f"Database already seeded ({n} entities). Skipping.")
        return

    ECI = "ECI affidavit portal (demo data)"
    MCA = "MCA master data (demo data)"
    CPPP = "CPPP eProcure (demo data)"
    GEM = "GeM portal (demo data)"
    PFMS = "PFMS dashboard (demo data)"

    # ---------- Case 1: Arvind Rathod — family-firm contracts + asset growth + ghost entity ----------
    rathod = ent(c, "Arvind Rathod", "Politician", pan="DEMOP0001A", party="Demo Vikas Party",
                 position="Member of Parliament (Lok Sabha)", constituency="Nandipur", state="Maharashtra",
                 criminal_cases=2, notes="FICTIONAL demo politician")
    sunita = ent(c, "Sunita Rathod", "Person", din="00900001", pan="DEMOP0002B", state="Maharashtra",
                 notes="Spouse of Arvind Rathod (fictional)")
    mahesh = ent(c, "Mahesh Rathod", "Person", din="00900002", pan="DEMOP0003C", state="Maharashtra",
                 address="14 Bazar Peth, Nandipur", notes="Brother of Arvind Rathod (fictional)")
    sn_infra = ent(c, "Shree Nandipur Infrastructure Pvt Ltd", "Company", cin="U45200MH2015PTC900001",
                   pan="DEMOC0001D", state="Maharashtra", address="14 Bazar Peth, Nandipur",
                   incorporation_date="2015-03-12")
    agro = ent(c, "Rathod Agro Traders Pvt Ltd", "Company", cin="U01100MH2018PTC900002", pan="DEMOC0002E",
               state="Maharashtra", address="14 Bazar Peth, Nandipur", incorporation_date="2018-07-01")
    ghost = ent(c, "Jai Bharat Suppliers Pvt Ltd", "Company", cin="U51900MH2023PTC900003", pan="DEMOC0003F",
                state="Maharashtra", address="14 Bazar Peth, Nandipur", incorporation_date="2023-08-04")
    trust = ent(c, "Nandipur Seva Charitable Trust", "Trust", state="Maharashtra",
                notes="Trustee: Sunita Rathod (fictional)")
    pwd_mh = ent(c, "PWD Maharashtra — Nandipur Division", "GovtBody", state="Maharashtra")
    dist_auth = ent(c, "Nandipur District Development Authority", "GovtBody", state="Maharashtra")

    rel(c, rathod, sunita, "Family_Link", "Spouse declared in 2024 affidavit", ECI)
    rel(c, rathod, mahesh, "Family_Link", "Brother named in 2019 affidavit dependents", ECI)
    rel(c, sunita, sn_infra, "Director_Of", "DIN 00900001 appointed 2016-01-20", MCA, "2016-01-20")
    rel(c, mahesh, sn_infra, "Director_Of", "DIN 00900002 appointed 2015-03-12", MCA, "2015-03-12")
    rel(c, mahesh, agro, "Director_Of", "DIN 00900002 appointed 2018-07-01", MCA, "2018-07-01")
    rel(c, mahesh, ghost, "Director_Of", "DIN 00900002 appointed 2023-08-04", MCA, "2023-08-04")
    rel(c, sunita, trust, "Director_Of", "Trustee per trust deed extract", "State charity registrar (demo)")
    rel(c, rathod, pwd_mh, "Oversees", "Member, district infrastructure committee", "Lok Sabha committee list (demo)")
    rel(c, rathod, dist_auth, "Directs_Funds_To", "MPLADS recommendations FY22-FY25", PFMS)
    rel(c, agro, ghost, "Shared_Address", "Registered office identical: 14 Bazar Peth, Nandipur", MCA)

    decl(c, rathod, 2014, 2.1 * CR, 0.4 * CR, 18 * L)
    decl(c, rathod, 2019, 18.4 * CR, 1.1 * CR, 32 * L)
    decl(c, rathod, 2024, 61.0 * CR, 2.6 * CR, 41 * L)

    tenure(c, rathod, "Member of Parliament (Lok Sabha)", "2014-05-16", "2019-05-23")
    tenure(c, rathod, "Member of Parliament (Lok Sabha)", "2019-05-24", "2024-06-03")
    tenure(c, rathod, "Chairperson, District Infrastructure Development Committee", "2021-01-10")

    financials(c, sn_infra, 2020, 5.0 * CR, 2.0 * CR, 4.0 * CR, 0.5 * CR)
    financials(c, sn_infra, 2021, 8.0 * CR, 3.0 * CR, 6.0 * CR, 1.0 * CR)
    financials(c, sn_infra, 2022, 12.0 * CR, 4.0 * CR, 10.0 * CR, 1.8 * CR)

    financials(c, ghost, 2023, 0.1 * CR, 0.05 * CR, 0.2 * CR, 0.02 * CR)

    contract(c, "PWD/NDP/2021/114", "Nandipur ring road widening Phase I", pwd_mh, sn_infra, 12.5 * CR, "2021-02-18", "Road widening 14 km", CPPP)
    contract(c, "PWD/NDP/2022/067", "Rural road resurfacing package B", pwd_mh, sn_infra, 9.8 * CR, "2022-06-30", "Resurfacing 22 villages", CPPP)
    contract(c, "PWD/NDP/2023/021", "Nandipur bypass culvert works", pwd_mh, sn_infra, 14.2 * CR, "2023-01-12", "Culverts and drainage", CPPP)
    contract(c, "PWD/NDP/2024/090", "Ring road Phase II earthworks", pwd_mh, sn_infra, 10.5 * CR, "2024-03-22", "Earthworks and compaction", CPPP)
    contract(c, "GEM/2023/B/779912", "Supply of street lighting fixtures", dist_auth, ghost, 6.2 * CR, "2023-08-15", "LED street lighting, district towns", GEM)

    flow(c, "MPLADS", dist_auth, pwd_mh, 18 * CR, "2022-04-05", "MP-recommended road works allocation", PFMS)
    flow(c, "MPLADS", dist_auth, pwd_mh, 21 * CR, "2023-04-11", "MP-recommended infra allocation", PFMS)
    flow(c, "CSR/Donation", sn_infra, trust, 1.9 * CR, "2023-09-30", "CSR donation to trust", MCA)
    flow(c, "Trust disbursal", trust, agro, 1.4 * CR, "2024-01-15", "Procurement of relief material", "Trust filings (demo)")
    flow(c, "Intercompany loan", agro, sn_infra, 1.2 * CR, "2024-03-02", "Unsecured loan to group company", MCA)

    # ---------- Case 2: Kavita Deshmane — repeated awards + donor link ----------
    kavita = ent(c, "Kavita Deshmane", "Politician", pan="DEMOP0011G", party="Demo Janata Morcha",
                 position="MLA & Chairperson, District Tender Committee", constituency="Hosakere",
                 state="Karnataka", criminal_cases=0, notes="FICTIONAL demo politician")
    prakash = ent(c, "Prakash Hegde", "Person", din="00900011", pan="DEMOP0012H", state="Karnataka",
                  notes="Election donor and director (fictional)")
    vij_con = ent(c, "Vijaya Constructions Pvt Ltd", "Company", cin="U45200KA2012PTC900011", pan="DEMOC0011I",
                  state="Karnataka", incorporation_date="2012-05-09")
    hosa_dept = ent(c, "Hosakere Zilla Panchayat Works Dept", "GovtBody", state="Karnataka")

    rel(c, prakash, vij_con, "Director_Of", "DIN 00900011 appointed 2012-05-09", MCA, "2012-05-09")
    rel(c, prakash, kavita, "Donor_To", "₹85L electoral donation FY2023 (demo electoral bond extract)", "Electoral disclosures (demo)", value=85 * L)
    rel(c, kavita, hosa_dept, "Oversees", "Chairperson, district tender committee", "State gazette (demo)")

    decl(c, kavita, 2018, 3.4 * CR, 0.2 * CR, 22 * L)
    decl(c, kavita, 2023, 9.1 * CR, 0.5 * CR, 28 * L)

    for i, (val, dt) in enumerate([
        (3.1 * CR, "2022-01-20"), (2.4 * CR, "2022-05-14"), (4.0 * CR, "2022-11-02"),
        (2.8 * CR, "2023-03-19"), (3.6 * CR, "2023-09-27"), (5.2 * CR, "2024-02-08"),
        (2.2 * CR, "2024-07-16"), (3.9 * CR, "2025-01-30"),
    ]):
        contract(c, f"KA/HZP/{dt[:4]}/{200 + i}", f"Panchayat civil works package {i + 1}",
                 hosa_dept, vij_con, val, dt, "Civil works under district plan", CPPP)
    other_co = ent(c, "Karnataka BuildWell Ltd", "Company", cin="U45200KA2010PLC900012", state="Karnataka",
                   incorporation_date="2010-02-15")
    contract(c, "KA/HZP/2022/199", "School compound walls", hosa_dept, other_co, 1.1 * CR, "2022-02-01", "Compound walls", CPPP)
    contract(c, "KA/HZP/2023/240", "Anganwadi repairs", hosa_dept, other_co, 0.9 * CR, "2023-06-12", "Repairs", CPPP)

    # ---------- Case 3: clean low-risk politician for contrast ----------
    imran = ent(c, "Imran Shaikh", "Politician", pan="DEMOP0021J", party="Demo Vikas Party",
                position="Member of Parliament (Lok Sabha)", constituency="Charbagh", state="Uttar Pradesh",
                criminal_cases=0, notes="FICTIONAL demo politician — clean profile")
    decl(c, imran, 2019, 1.2 * CR, 0.1 * CR, 19 * L)
    decl(c, imran, 2024, 1.9 * CR, 0.1 * CR, 24 * L)

    # ---------- Filler entities for stats / explore ----------
    fillers = [
        ("Meera Pillai", "Politician", "Kerala", "Thirumala", "Demo Janata Morcha"),
        ("Harpreet Gill", "Politician", "Punjab", "Rajgarh", "Demo Vikas Party"),
        ("Ananya Bose", "Politician", "West Bengal", "Ichapur", "Demo Lok Shakti"),
        ("Devraj Naik", "Politician", "Odisha", "Kantapali", "Demo Lok Shakti"),
        ("Ritu Chauhan", "Politician", "Rajasthan", "Bhilwara South", "Demo Janata Morcha"),
    ]
    for name, t, st, cons, party in fillers:
        eid = ent(c, name, t, state=st, constituency=cons, party=party, notes="FICTIONAL demo politician")
        decl(c, eid, 2019, 1.5 * CR, 0.2 * CR, 20 * L)
        decl(c, eid, 2024, 2.6 * CR, 0.3 * CR, 26 * L)

    conn.commit()
    print("Seeded fictional demo data:",
          c.execute("SELECT COUNT(*) FROM entities").fetchone()[0], "entities,",
          c.execute("SELECT COUNT(*) FROM contracts").fetchone()[0], "contracts,",
          c.execute("SELECT COUNT(*) FROM relationships").fetchone()[0], "relationships")


if __name__ == "__main__":
    seed()
