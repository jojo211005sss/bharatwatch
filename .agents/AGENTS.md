# Agent Guidelines for BharatWatch Data Integrity

These guidelines are established to maintain the strict credibility and factual correctness of the BharatWatch database. They constrain agent behavior to prevent hallucinations, fictionalizations, and false verification claims.

## 1. Zero Tolerance for Fake Data under Real Politicians
* **No Fictional Entities**: Do not seed or insert fictional family members (like mock brothers/sisters) or fictional shell companies under a real politician's profile to trigger rules.
* **No Simulated Fund Loops**: Do not simulate circular fund flows (like fake trust donations) that are not backed by official public records.
* **Fictional Profiles**: Only the explicitly designated fictional demo profile (e.g., Arvind Rathod) may contain fictional demonstration data. These demo profiles must be clearly labeled as fictional.

## 2. Strict Source Document Verification
* **Clickable, Direct Links**: Every source entry in the database must point to the exact document, news article, or master record page that proves the claim.
* **Identifier Matches**: When linking a record, the target page must explicitly contain the core identifier (the first name of a person or the unique core name of a company). Surnames or common words are not sufficient.
* **No Placeholders**: Do not use home pages (like `http://delhi.gov.in/` or `https://pfms.nic.in/`) as source URLs for specific relationship/contract/fund-flow claims unless the homepage itself explicitly contains the detailed record.

## 3. Mandatory Verification Workflow
* Whenever seed files or database importers are modified, the verification script `verify_sources.py` must be executed.
* The script must be run with strict keyword matching enabled to catch missing or hallucinated references. Any warnings or failures must be addressed by correcting the database records, not by adding exceptions or bypassing checks.
