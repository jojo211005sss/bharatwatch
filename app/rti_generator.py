"""Dynamic RTI suggestion generator for BharatWatch red-flagged patterns."""

def generate_rti_suggestion(pattern, evidence, pol_name):
    """Generate target Public Authority and draft RTI queries based on flag pattern and evidence."""
    if not evidence:
        return None

    authority = "Public Information Officer (PIO)"
    draft_queries = []

    if pattern == "LOAN_CONFLICT":
        # Extract contractor, family companies, and contracts from evidence list
        contractor = evidence[0].get("supplier", "the contractor")
        
        # Try to parse family company and loan info
        loan_ev = evidence[0].get("loan_evidence", "")
        family_company = "family-linked companies"
        if "cian" in loan_ev.lower():
            family_company = "CIAN Agro Industries & Infrastructure Limited"
        elif "purti" in loan_ev.lower():
            family_company = "Purti Group / CIAN Agro"
        
        # Build tender titles
        tenders = [item.get("title") for item in evidence if item.get("title")]
        tenders_str = " / ".join(f"'{t}'" for t in tenders) if tenders else "relevant highway construction projects"
        
        # Target NHAI or MoRTH
        buyers = {item.get("buyer") for item in evidence if item.get("buyer")}
        buyer_name = list(buyers)[0] if buyers else "National Highways Authority of India (NHAI)"
        
        authority = f"Public Information Officer (PIO), {buyer_name}"
        draft_queries = [
            f"1. Certified copies of the contract agreements, notice inviting tenders (NIT), technical evaluation reports, and minutes of the tender committee meetings for the projects: {tenders_str} awarded to {contractor}.",
            f"2. Certified copies of the conflict-of-interest declarations or disclosures (if any) submitted by the tender evaluation committee members or the Union Minister's office regarding relationships/transactions between {contractor} and {family_company}.",
            f"3. Certified copies of file notings, committee decisions, and approval sheets relating to the concession agreements, toll collection rights, and revisions for the project(s) awarded to {contractor}."
        ]

    elif pattern == "POLICY_CONFLICT":
        suppliers = {item.get("supplier") for item in evidence if item.get("supplier")}
        suppliers_str = " and ".join(suppliers) if suppliers else "family-linked ethanol manufacturing companies"
        
        buyers = {item.get("buyer") for item in evidence if item.get("buyer")}
        buyer_str = " and ".join(buyers) if buyers else "BPCL / HPCL"
        
        authority = f"Public Information Officer (PIO), Ministry of Petroleum and Natural Gas (MoPNG) / {buyer_str}"
        draft_queries = [
            f"1. Certified copies of the supply orders, purchase agreements, and tender selection documents for the ethanol supply contracts awarded to {suppliers_str} for the financial years 2020-2026.",
            f"2. Certified copies of the rules, guidelines, pricing structures, and subsidies established by the Ministry or public sector oil marketing companies (OMCs) for the procurement of ethanol from private distilleries.",
            f"3. Certified copies of all representations, letters, or correspondence received from {suppliers_str} or their directors (including Nikhil Gadkari and Sarang Gadkari) regarding ethanol blending pricing, mandates, or feedstock guidelines."
        ]

    elif pattern == "FAMILY_CONTRACT":
        suppliers = {item.get("supplier") for item in evidence if item.get("supplier")}
        suppliers_str = " and ".join(suppliers) if suppliers else "family-linked companies"
        
        buyers = {item.get("buyer") for item in evidence if item.get("buyer")}
        buyer_str = " / ".join(buyers) if buyers else "the buyer department"
        
        authority = f"Public Information Officer (PIO), {buyer_str}"
        draft_queries = [
            f"1. Certified copies of the tender documents, bid evaluation sheets, and final work orders awarded to {suppliers_str} under the overseen departments.",
            f"2. Certified copy of the conflict-of-interest declarations filed by the bidding companies ({suppliers_str}) or the overseeing officers regarding the relationship of directors with the Union Minister.",
            f"3. Details of all payments made to {suppliers_str} for the projects won under this department, along with physical completion/inspection certificates."
        ]

    elif pattern == "ASSET_GROWTH":
        state = evidence[0].get("state", "")
        auth_suffix = f", Legislative Assembly Secretariat of {state}" if state else " / Election Commission of India (ECI)"
        authority = f"Public Information Officer (PIO){auth_suffix}"
        
        years = [item.get("year") for item in evidence if item.get("year")]
        year_str = f"from {min(years)} to {max(years)}" if years else "for the last 3 election cycles"
        
        draft_queries = [
            f"1. Certified copies of the annual asset and liability statements (along with annexures and income declarations) filed by MLA/MP {pol_name} under the relevant Code of Conduct or Service Rules {year_str}.",
            f"2. Details of any discrepancies identified, queries raised, or verification actions taken by the competent authority regarding the asset declarations of {pol_name}."
        ]

    elif pattern == "REPEATED_AWARDS":
        suppliers = {item.get("supplier") for item in evidence if item.get("supplier")}
        suppliers_str = " and ".join(suppliers) if suppliers else "the contractor"
        
        buyers = {item.get("buyer") for item in evidence if item.get("buyer")}
        buyer_str = " / ".join(buyers) if buyers else "the department"
        
        authority = f"Public Information Officer (PIO), {buyer_str}"
        draft_queries = [
            f"1. A statement listing all contracts awarded to {suppliers_str} by this department/ministry over the last 5 years, along with tender values, completion status, and competing bidder counts.",
            f"2. Certified copies of any single-bid justifications or proprietary certificate notes issued to circumvent open bidding for awards given to {suppliers_str}.",
            f"3. Certified copies of the performance audits and completion reports of the projects executed by {suppliers_str}."
        ]

    elif pattern == "GHOST_ENTITY":
        comp = evidence[0].get("company", "the company")
        cin = evidence[0].get("cin", "N/A")
        first_award = evidence[0].get("first_award", {})
        tender_id = first_award.get("tender_id", "N/A")
        
        authority = f"Public Information Officer (PIO), Ministry of Corporate Affairs (MCA), Registrar of Companies (RoC)"
        draft_queries = [
            f"1. Certified copies of Form INC-22 (Verification of Registered Office), along with physical verification reports, site photos, or inspection notes for company {comp} (CIN: {cin}).",
            f"2. Certified copies of beneficial interest declarations (Form MGT-6 or BEN-2) filed by {comp} under Section 89/90 of the Companies Act, 2013.",
            f"3. Certified copies of work completion certificates, engineer inspection reports, and billing files for works executed by {comp} under Tender ID {tender_id}."
        ]

    elif pattern == "FUND_LOOP":
        trust = evidence[0].get("trust_name", "the trust")
        scheme = evidence[0].get("scheme", "the scheme")
        
        authority = f"Public Information Officer (PIO), District Collector / Public Financial Management System (PFMS)"
        draft_queries = [
            f"1. Certified copies of the trust deed, registration certificate, and annual audited financial statements of the trust/society {trust}.",
            f"2. Certified copies of the scheme utilization certificates (UCs) and progress reports submitted by {trust} for receiving funds under the scheme '{scheme}'.",
            f"3. Details of all donations received by {trust} above Rs 20,000, along with PAN and address details of the donors."
        ]

    else:
        # General/default patterns
        authority = f"Public Information Officer (PIO) of the relevant department/agency"
        draft_queries = [
            f"1. Certified copies of all bid evaluation sheets, approvals, and contract agreements related to the transactions involving {pol_name} or linked entities.",
            f"2. Copy of conflict-of-interest declarations or disclosures filed by the committee members concerning the award.",
            f"3. Details of all payments, audited balance sheets, and completion certificates associated with the work."
        ]

    return {
        "authority": authority,
        "draft": "\n".join(draft_queries)
    }
