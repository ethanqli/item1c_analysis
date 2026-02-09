## EDGAR 10-K Item-1C Extraction Pipeline

### Overview
This repository contains a small pipeline for collecting and analyzing
Item 1C (Cybersecurity) disclosures from U.S. public company 10-K filings
using the SEC EDGAR system.

### Data Collection
- Enumerates filings via the EDGAR daily master index (.idx)
- Filters to Form Type = 10-K
- Resolves each filing to its primary HTML document via the filing index page
- Downloads and parses the HTML from sec.gov/Archives

### Extraction
- Converts HTML to plain text
- Extracts Item 1C

### Manual Observations
- Standardized information
- No significant differences across firms, mostly generic language
- Security awareness training is frequently mentioned
- Third-party risk is frequently mentioned but minimally detailed

### List of Related Work
- https://www.scirp.org/journal/paperinformation?paperid=146412
- https://www.knowntrends.com/2024/03/snapshot-form-10-k-cybersecurity-disclosures/
