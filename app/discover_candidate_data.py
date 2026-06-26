#!/usr/bin/env python3
"""Auto-discovery tool for BharatWatch.

Searches the web for news, scam reports, and company links related to a politician
using DuckDuckGo HTML search, then uses Agent-Reach's WebChannel (Jina Reader)
to extract clean text and verify source quality.
"""
import argparse
import urllib.request
import urllib.parse
import ssl
import re
import time
import sys

# Ensure SSL bypass for macOS Python environments
ssl._create_default_https_context = ssl._create_unverified_context

try:
    from agent_reach.channels.web import WebChannel
    AGENT_REACH_AVAILABLE = True
except ImportError:
    AGENT_REACH_AVAILABLE = False
    class WebChannel:
        def read(self, url):
            # Fallback simple reader
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")

def search_ddg(query, num_results=8):
    """Query DuckDuckGo HTML search using a POST request."""
    url = "https://html.duckduckgo.com/html/"
    data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    try:
        time.sleep(1.5) # Respectful delay
        with urllib.request.urlopen(req, timeout=12) as response:
            html = response.read().decode("utf-8", errors="ignore")
            # Extract links using regex
            links = re.findall(r'<a class="result__url" href="([^"]+)"', html)
            # Clean and filter duplicates
            seen = set()
            unique_links = []
            for link in links:
                decoded = urllib.parse.unquote(link)
                # Filter out DDG internal links
                if "duckduckgo.com" in decoded or not decoded.startswith("http"):
                    continue
                if decoded not in seen:
                    seen.add(decoded)
                    unique_links.append(decoded)
                if len(unique_links) >= num_results:
                    break
            return unique_links
    except Exception as e:
        print(f"Error searching DuckDuckGo for query '{query}': {e}", file=sys.stderr)
        return []

def main():
    parser = argparse.ArgumentParser(description="BharatWatch Candidate Data Auto-Discovery Tool")
    parser.add_argument("name", help="Name of the politician to search for")
    parser.add_argument("--query-type", choices=["all", "scam", "business", "bonds"], default="all",
                        help="Focus area of the search queries")
    parser.add_argument("--limit", type=int, default=5, help="Number of URLs to fetch and analyze per query")
    args = parser.parse_args()

    print("==============================================================")
    print(f" BharatWatch Auto-Discovery Tool: {args.name}")
    print("==============================================================")
    if AGENT_REACH_AVAILABLE:
        print("⚡ Agent-Reach WebChannel (Jina Reader) active for parsing.")
    else:
        print("⚠️ Agent-Reach not found. Falling back to basic HTTP parsing.")

    # Build queries
    queries = []
    if args.query_type in ("all", "scam"):
        queries.append(f"{args.name} scam CBI")
    if args.query_type in ("all", "business"):
        queries.append(f"{args.name} director company")
    if args.query_type in ("all", "bonds"):
        queries.append(f"{args.name} electoral bonds")

    discovered_urls = {}

    for q in queries:
        print(f"\nSearching: '{q}'...")
        urls = search_ddg(q, num_results=args.limit)
        print(f" -> Found {len(urls)} candidates.")
        for url in urls:
            if url not in discovered_urls:
                discovered_urls[url] = q

    if not discovered_urls:
        print("\nNo candidate URLs found.")
        sys.exit(0)

    print(f"\nAnalyzing {len(discovered_urls)} unique candidate URLs...")
    web = WebChannel()
    
    results = []
    for idx, (url, query) in enumerate(discovered_urls.items(), 1):
        print(f"[{idx}/{len(discovered_urls)}] Fetching & verifying: {url}")
        try:
            content = web.read(url).lower()
            # Calculate simple keyword counts
            name_words = [w.strip().lower() for w in args.name.split() if len(w.strip()) > 3]
            match_counts = {word: content.count(word) for word in name_words}
            
            # Simple assessment of content relevancy
            relevance = "High" if any(count >= 3 for count in match_counts.values()) else "Medium" if any(count > 0 for count in match_counts.values()) else "Low"
            
            # Look for evidence terms
            scam_mentions = sum(content.count(term) for term in ["scam", "fraud", "corruption", "bribe", "cbi", "ed"])
            company_mentions = sum(content.count(term) for term in ["director", "company", "board", "shareholder", "bonds"])
            
            results.append({
                "url": url,
                "query": query,
                "relevance": relevance,
                "scam_mentions": scam_mentions,
                "company_mentions": company_mentions,
                "keyword_matches": match_counts
            })
        except Exception as e:
            print(f"   ❌ Fetch failed: {e}")
            results.append({
                "url": url,
                "query": query,
                "relevance": "Error",
                "scam_mentions": 0,
                "company_mentions": 0,
                "keyword_matches": {}
            })

    # Sort results by relevance (High -> Medium -> Low -> Error)
    rel_map = {"High": 3, "Medium": 2, "Low": 1, "Error": 0}
    results.sort(key=lambda r: rel_map.get(r["relevance"], 0), reverse=True)

    print("\n================== DISCOVERY REPORT ==================")
    print(f"{'URL':<60} | {'Relevance':<10} | {'Scam Terms':<10} | {'Biz Terms':<10}")
    print("-" * 100)
    for r in results:
        # Truncate URL if too long
        disp_url = r["url"] if len(r["url"]) <= 58 else r["url"][:55] + "..."
        print(f"{disp_url:<60} | {r['relevance']:<10} | {r['scam_mentions']:<10} | {r['company_mentions']:<10}")
        if r["keyword_matches"]:
            print(f"   ↳ Keywords matched: {r['keyword_matches']}")
    print("======================================================")

if __name__ == "__main__":
    main()
