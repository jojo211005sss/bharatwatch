# BharatWatch — Standard Operating Procedure (for research assistants)

**What this app does:** You feed it public records (politician asset declarations, company
records, government contracts). It draws a map of who is connected to whom, and raises a
red flag when a suspicious pattern appears — for example, a politician's brother's company
winning many government contracts.

**Your job:** Collect records from official websites, type them into simple spreadsheet
files, upload them, and check the red flags the app raises.

**Golden rule:** We collect facts and save proof. We NEVER say anyone is corrupt — not in
the app, not on WhatsApp, not anywhere. Only the team lead decides what happens with a
finished case file.

---

## Words you will see

| Word | Meaning |
|---|---|
| Affidavit | A sworn form every election candidate files. Lists their money, property, family, court cases. |
| PAN | Tax ID number of a person or company (like ABCDE1234F). |
| DIN | Director ID Number. Every company director in India has one. Never changes. |
| CIN | Company ID number (long code starting with U or L). |
| Tender | A government "we want to buy something" notice. The winner gets the contract. |
| Crore (Cr) | ₹1,00,00,000 (ten million rupees). |

---

## PART A — Practice run (30 minutes, fake data, nothing can go wrong)

The app comes with a made-up politician called **Arvind Rathod** so you can learn the
screens. He is not a real person.

1. Open the app in your browser: **http://localhost:8787** (or the team's hosted address —
   ask your lead).
2. In the big search box, type `Rathod`. Click **Arvind Rathod**.
3. Look at the top card. Note the **96%** risk score and the **₹ flagged** amount.
4. Scroll to **Relationship graph**. This is the map:
   - Red circle = politician. Gold/brown = family. Blue = company. Green = government office. Purple = trust.
   - The red double ring means "this one has red flags".
   - **Click any circle** to jump to that person/company. Click your browser's Back button to return.
   - **Click any arrow** — a box appears showing the proof behind that connection and which website it came from.
   - Try the **L1 / L2 / L3** buttons. L1 = direct connections only. L3 = friends of friends.
5. Scroll to **Flagged insights**. Read each red box slowly. Every box tells you:
   what was found, the risk %, the money involved, and (click "Evidence records") the
   exact records behind it.
6. Try the tabs: **Timeline** (every event in date order — this is where patterns jump out),
   **Companies**, **Contracts**, **Fund flows**, **Assets**.
7. Try the export buttons at the top: **PDF report** (save it — this is what a case file
   looks like), **CSV**, **JSON**, **Graph image**.

✅ You are done with Part A when you can answer: *"Which company won a contract just 11
days after it was created, and how is it connected to Arvind Rathod?"* (The answer is in
the flags.)

---

## PART B — A real case, step by step

Your lead will assign you ONE politician (example used below: "MP from constituency X").
Work on only that one. Going deep on one person beats shallow work on fifty.

You will fill small spreadsheet files (CSV). Make them in Google Sheets or Excel, then
**File → Download → CSV**. The column names in row 1 must match EXACTLY what is written
below. Money is always written in plain rupees with no commas (₹2.5 crore = `25000000`).
Dates are always `YYYY-MM-DD` (example: `2023-08-04`).

### Step 1 — Get the politician's asset history (45 min)

1. Go to **https://www.myneta.info/**
2. Type the politician's name in the search box. Open their page.
3. They will have one page per election (2014, 2019, 2024…). Open EACH one.
4. From each election page, write down: total assets, total liabilities, yearly income
   (from the income tax section), and number of criminal cases.
5. Also open the original scanned affidavit (linked on the page, or at
   **https://affidavit.eci.gov.in/**) and write down the **names of spouse and dependents**
   — you need these in Step 3. Save the PDF in the team folder as proof.

Make a file `affidavits.csv` with one row per election year:

```
name,pan,party,position,constituency,state,year,assets,liabilities,income,criminal_cases
Example Person,,Example Party,Member of Parliament,Example Constituency,Maharashtra,2014,21000000,4000000,1800000,2
Example Person,,Example Party,Member of Parliament,Example Constituency,Maharashtra,2019,184000000,11000000,3200000,2
```

(Leave `pan` empty — it is masked on public copies. The app matches by name + constituency.)

### Step 2 — Upload it

1. Open **http://localhost:8787/admin** and sign in (password from your lead).
2. In the dropdown choose **ECI affidavits**.
3. Click the file chooser, pick your `affidavits.csv`, click **Import & normalize**.
4. Read the message: it tells you how many rows went in and how many need review.
5. If the **review queue** below shows an item: it means the app is not sure whether the
   incoming row is the same person as someone already in the database. Read both names.
   Same person → click **Merge into match**. Different person → **Keep as new entity**.
   Not sure → ask your lead. Never guess.

### Step 3 — Add the family connections (15 min)

Make `relations.csv` from the affidavit family names you noted:

```
from_name,to_name,type,evidence,source
Example Person,Spouse Name,Family_Link,Spouse listed in 2024 affidavit page 3,ECI affidavit 2024
Example Person,Brother Name,Family_Link,Dependent listed in 2019 affidavit,ECI affidavit 2019
```

Upload it with dropdown set to **Relationships**.

Also find what the politician controls or influences:
- Lok Sabha MPs: **https://sansad.in/ls/members** → open the member's page → note ministry
  posts and committee memberships.
- For an MLA/minister, the state assembly website lists portfolios.

Add one row per body, with `type` = `Oversees` (committee/minister of that department) or
`Directs_Funds_To` (MPLADS/MLALAD recommendations go to the district authority):

```
Example Person,Public Works Department Maharashtra,Oversees,Member of infrastructure committee since 2021,Sansad.in member page
Example Person,Example District Development Authority,Directs_Funds_To,MPLADS recommendations,MPLADS portal
```

### Step 4 — Find the family's companies (1–2 hours; the most important step)

1. Go to **https://www.mca.gov.in/** → **MCA Services** → **Master Data** →
   **View Director Master Data**.
2. Search each family member's name. If you find them, write down the **DIN**.
   (Common names give many results — match using father's name/address region. Unsure = ask.)
3. Then use **View Companies/LLPs of Director** with that DIN → you get every company
   they direct. Write down each company's **CIN** and name.
4. For each company, use **View Company Master Data** with the CIN → write down the
   registered **address** and **date of incorporation**.
5. Take screenshots of every MCA result page → team folder.

Make two files and upload them (dropdowns: **MCA companies**, then **MCA directors**):

```
cin,name,pan,address,state,incorporation_date
U45200MH2015PTC900001,Example Infra Pvt Ltd,,14 Example Road Example Town,Maharashtra,2015-03-12
```

```
din,name,pan,cin,company_name,appointment_date
00900002,Brother Name,,U45200MH2015PTC900001,Example Infra Pvt Ltd,2015-03-12
```

👀 While doing this, note if two different companies share the SAME address — if yes, add
a row to `relations.csv` with `type` = `Shared_Address`.

### Step 5 — Get the contracts (2–3 hours)

You need ALL contract awards from the department(s) found in Step 3 — not just the
suspicious ones. (The app computes "this company won 8 of 11 contracts" — for that it
needs all 11.)

1. Go to **https://eprocure.gov.in/cppp/** → section **"Results of Tenders / Award of
   Contract"** → filter by the department/organisation name and your years.
2. Also check the state e-procurement portal (every state has one, e.g.
   mahatenders.gov.in for Maharashtra) — district works are usually there, not on CPPP.
3. For goods purchases, check **https://gem.gov.in/** (GeM) for orders by that buyer.
4. For each award write: tender number, what it was for, buyer office, winning company,
   amount, award date. Save the PDF/screenshot of each award notice.

```
tender_id,title,buyer,supplier,supplier_cin,value,award_date,description,source
PWD/2021/114,Ring road widening,Public Works Department Maharashtra,Example Infra Pvt Ltd,U45200MH2015PTC900001,125000000,2021-02-18,Road widening 14 km,CPPP award notice
```

Upload with dropdown **CPPP/GeM contracts**. Fill `supplier_cin` whenever you know it —
it guarantees the contract attaches to the right company.

### Step 6 — Get the fund flows (optional but powerful, 1 hour)

- **https://www.mplads.gov.in/** → reports → your MP → yearly recommended/spent amounts.
- **https://pfms.nic.in/** → scheme-wise reports for the district.

```
scheme,from,to,amount,date,purpose,source
MPLADS,Example District Development Authority,Public Works Department Maharashtra,180000000,2022-04-05,MP recommended road works,MPLADS portal report FY22
```

Upload with dropdown **PFMS fund flows**.

### Step 7 — Read the results (1 hour)

1. Go back to the home page, search your politician, open their profile.
2. The app has already re-checked everything after each upload (the button
   **Re-run detection only** forces it again).
3. For EVERY red flag box:
   - Read the explanation out loud. Does it make sense?
   - Click **Evidence records** and open every source document you saved. Does each link
     in the chain hold? (Same person? Same company? Right amounts? Right dates?)
   - Open the **Timeline** tab. The strongest pattern looks like: *money allocated → a
     company created or contract floated → award to a family company* — all within a few
     months, repeating.
4. Click **PDF report** and save it in the team folder as `CASENAME_draft1.pdf`.

### Step 8 — Hand over

Fill this in the team folder and tell your lead:

```
Politician:            ______________________
Flags raised by app:   ___ (list pattern names)
Flags I verified true: ___ (every evidence doc checked by hand)
Flags that look wrong: ___ (and why — wrong person matched? data entry error?)
Documents saved:       ___ affidavit PDFs, ___ MCA screenshots, ___ award notices
Things I could not find: ______________________
```

---

## Rules (read twice)

1. **Only public websites.** The ones listed above. Never pay anyone for data, never log
   into anything private, never scrape where a site forbids it.
2. **Every row needs a saved proof document** (PDF or screenshot) in the team folder. A
   row without proof gets deleted.
3. **Wrong data is worse than no data.** Not sure if two "Rajesh Kumar"s are the same
   person? Leave the item sitting in the review queue and ask your lead. Never guess.
4. **A red flag is a question, not an answer.** Innocent explanations are common — a
   relative's firm can win a tender fairly. Our job is to check, not to accuse.
5. **Nothing leaves the team.** No screenshots to friends, no social media posts.
   Publication decisions involve lawyers and editors, not us.
