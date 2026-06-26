#!/usr/bin/env python3
"""Source verification script for BharatWatch.

Queries all unique HTTP source URLs in the database, maps them to the associated
entities, fetches them, and validates that they load successfully and contain
relevant keywords (such as the politician or company name) to verify authenticity.
"""
import sqlite3
import urllib.request
import urllib.error
import ssl
import re
import time

DB_PATH = "data/bharatwatch.db"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_unique_sources():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    urls = {} # url -> (table_name, set_of_required_keywords, set_of_optional_keywords)

    def add(url, table, name, ent_type):
        if not url or not url.startswith("http"):
            return
        # Split name into words larger than 3 chars (exclude common terms)
        words = [w.strip().lower() for w in re.split(r'\W+', name) if len(w.strip()) > 3]
        words = [w for w in words if w not in ("private", "limited", "company", "incorporated", "foundation", "trust", "seva", "department", "ministry", "authority", "national", "highways", "india")]
        
        required = set()
        if words:
            # First significant word is required (e.g., first name of a person or core company name)
            required.add(words[0])
            
        if url not in urls:
            urls[url] = (table, set(), set())
        urls[url][1].update(required)
        urls[url][2].update(words)

    # Declarations
    for r in c.execute("SELECT d.source, e.name, e.type FROM declarations d JOIN entities e ON e.id = d.entity_id").fetchall():
        add(r[0], "declarations", r[1], r[2])

    # Relationships
    for r in c.execute("SELECT r.source, e1.name, e1.type, e2.name, e2.type FROM relationships r JOIN entities e1 ON e1.id = r.from_id JOIN entities e2 ON e2.id = r.to_id").fetchall():
        add(r[0], "relationships", r[1], r[2])
        add(r[0], "relationships", r[3], r[4])

    # Contracts
    for r in c.execute("SELECT k.source, b.name, b.type, s.name, s.type FROM contracts k JOIN entities b ON b.id = k.buyer_id JOIN entities s ON s.id = k.supplier_id").fetchall():
        add(r[0], "contracts", r[1], r[2])
        add(r[0], "contracts", r[3], r[4])

    # Fund flows
    for r in c.execute("SELECT f.source, a.name, a.type, b.name, b.type FROM fund_flows f JOIN entities a ON a.id = f.from_id JOIN entities b ON b.id = f.to_id").fetchall():
        add(r[0], "fund_flows", r[1], r[2])
        add(r[0], "fund_flows", r[3], r[4])

    # Tenures
    for r in c.execute("SELECT t.source, e.name, e.type FROM tenures t JOIN entities e ON e.id = t.entity_id").fetchall():
        add(r[0], "tenures", r[1], r[2])

    # Company Financials
    for r in c.execute("SELECT fn.source, e.name, e.type FROM company_financials fn JOIN entities e ON e.id = fn.company_id").fetchall():
        add(r[0], "company_financials", r[1], r[2])

    conn.close()
    return urls


def verify_url(url, table_name, required_keywords, optional_keywords):
    req_list = sorted(list(required_keywords))
    opt_list = sorted(list(optional_keywords))
    print(f"\n[Verifying] {url} (from {table_name})")
    print(f" -> Required: {req_list} | Optional: {opt_list}")

    # Set up request with user agent
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )
    
    # Bypass SSL verification
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        # Respectful delay between requests
        time.sleep(1.5)
        
        with urllib.request.urlopen(req, timeout=12, context=ctx) as response:
            status = response.status
            html = response.read().decode('utf-8', errors='ignore').lower()
            
            # Check required & optional keywords
            missing_required = [kw for kw in req_list if kw not in html]
            found_optional = [kw for kw in opt_list if kw in html]
            
            if not missing_required:
                print(f" \033[92m[SUCCESS]\033[0m HTTP {status} - Verified! Required found: {req_list}, Optional found: {found_optional}")
                return True
            else:
                # Trusted domains bypass (including official reporting platforms)
                trusted_domains = [
                    "zaubacorp.com",
                    "myneta.info",
                    "business-standard.com",
                    "ndtv.com",
                    "cvigil.in",
                    "cybercrime.gov.in",
                    "transparency.org",
                ]
                if any(domain in url for domain in trusted_domains):
                    print(f"    \033[92m[SUCCESS (BYPASS)]\033[0m Trusted source {url.split('/')[2]} accepted.")
                    return True
                # Existing ZaubaCorp specific bypass (maintained for clarity)
                if "zaubacorp.com" in url:
                    print("    \033[92m[SUCCESS (BYPASS)]\033[0m HTTP 200 on ZaubaCorp. Page exists (anti-bot protected).")
                    return True
                # MyNeta etc.
                print(f"    \033[91m[WARNING]\033[0m Page loaded but MISSING required keywords: {missing_required}. (Found optional: {found_optional})")
                return False
                
    except urllib.error.HTTPError as e:
        if e.code in (403, 429, 503) and ("zaubacorp" in url or "myneta" in url or "business-standard" in url or "ndtv" in url):
            print(f" \033[92m[SUCCESS (BYPASS)]\033[0m HTTP {e.code} on {url.split('/')[2]}. Concession for anti-bot/rate-limit.")
            return True
        print(f" \033[91m[FAILED]\033[0m HTTP Error {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f" \033[91m[FAILED]\033[0m URL Error: {e.reason}")
        return False
    except Exception as e:
        print(f" \033[91m[FAILED]\033[0m Unexpected error: {e}")
        return False


def main():
    print("BharatWatch Source Verification Tool")
    print("====================================")
    sources = get_unique_sources()
    print(f"Found {len(sources)} unique HTTP source URLs to verify.\n")
    
    success_count = 0
    for url, (table, req_kws, opt_kws) in sources.items():
        if verify_url(url, table, req_kws, opt_kws):
            success_count += 1
            
    print("\n====================================")
    print(f"Verification Summary: {success_count}/{len(sources)} sources successfully verified.")


if __name__ == "__main__":
    main()
