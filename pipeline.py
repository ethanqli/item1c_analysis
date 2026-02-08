import re
import time
from pathlib import Path
from io import StringIO

import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


UA = "Ethan Li (ethanli@uchicago.edu)"
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}

INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/2026/QTR1/master.20260206.idx"


# ---------- Utilities ----------

def normalize_sec_url(url: str) -> str:
    """
    Convert SEC iXBRL viewer URLs like:
      https://www.sec.gov/ix?doc=/Archives/edgar/data/.../file.htm
    into the raw Archives URL:
      https://www.sec.gov/Archives/edgar/data/.../file.htm
    """
    if "/ix" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        doc = qs.get("doc", [None])[0]
        if doc:
            return "https://www.sec.gov" + doc
    return url


def download(url: str) -> str:
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
    time.sleep(0.25)  # be polite to SEC
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    return r.text

def save_text(s: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8")

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # optional: remove tables to reduce noise
    for t in soup.find_all("table"):
        t.decompose()

    text = soup.get_text("\n")
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ---------- Item 1C extractor (works well on .htm->text) ----------
def extract_item_1c(text: str) -> str | None:
    lines = text.splitlines()

    # Start: try a strict header line first
    start_pat = re.compile(r"(?im)^\s*item\s*1c\s*[\.\:\-\—]?\s*(cybersecurity)?\s*$")
    loose_start = re.compile(r"(?i)\bitem\s*1c\b")

    # End: next item header (common next sections)
    end_pat = re.compile(r"(?im)^\s*item\s*(1d|2|3|4|5|6|7|7a|8|9|9a|9b|10|11|12|13|14|15)\b")

    start_idx = None
    for i, line in enumerate(lines):
        if start_pat.search(line.strip()):
            start_idx = i
            break
    if start_idx is None:
        for i, line in enumerate(lines):
            if loose_start.search(line):
                start_idx = i
                break
    if start_idx is None:
        return None

    end_idx = None
    for j in range(start_idx + 1, len(lines)):
        if end_pat.search(lines[j].strip()):
            end_idx = j
            break

    chunk = "\n".join(lines[start_idx:end_idx] if end_idx else lines[start_idx:]).strip()
    return chunk if len(chunk) >= 400 else None


# ---------- Master index (.idx) loader ----------
def load_master_idx(url: str) -> pd.DataFrame:
    raw = download(url)
    lines = raw.splitlines()

    # Data rows begin at the first line starting with a digit (CIK)
    data_start = next(i for i, line in enumerate(lines) if line and line[0].isdigit())

    df = pd.read_csv(
        StringIO("\n".join(lines[data_start:])),
        sep="|",
        names=["CIK", "Company Name", "Form Type", "Date Filed", "Filename"],
    )
    df.columns = df.columns.str.strip()
    return df


# ---------- From master-index Filename -> filing index page -> primary 10-K HTML ----------
def filing_index_url_from_master_filename(filename: str) -> str:
    # filename example: edgar/data/1035443/0001035443-26-000013.txt
    parts = filename.split("/")
    cik = parts[2]
    accession_with_dashes = Path(parts[-1]).stem         # 0001035443-26-000013
    accession_no_dashes = accession_with_dashes.replace("-", "")  # 000103544326000013

    return (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik}/{accession_no_dashes}/{accession_with_dashes}-index.htm"
    )


def primary_10k_html_url_from_index(index_url: str) -> str | None:
    """
    Parses the -index.htm page and tries to find the primary HTML file for the 10-K.
    """
    index_html = download(index_url)
    soup = BeautifulSoup(index_html, "lxml")

    # SEC index pages have a table listing documents
    for row in soup.select("table tr"):
        tds = row.find_all("td")
        if len(tds) < 4:
            continue

        doc_name = tds[0].get_text(strip=True)
        doc_type = tds[3].get_text(strip=True)

        if doc_type.upper() == "10-K" and doc_name.lower().endswith((".htm", ".html")):
            a = tds[0].find("a")
            if a and a.get("href"):
                return "https://www.sec.gov" + a["href"]

    # Fallback: first .htm in table (less precise)
    for a in soup.select("table a[href]"):
        href = a["href"]
        if href.lower().endswith((".htm", ".html")):
            return "https://www.sec.gov" + href

    return None


# ---------- Per-filing processing ----------
def process_filing(row: pd.Series) -> None:
    filename = row["Filename"]
    cik = str(row["CIK"]).strip()
    date_filed = str(row["Date Filed"]).strip()
    accession = Path(filename).stem  # e.g., 0001035443-26-000013

    base = f"{cik}_{date_filed}_{accession}"

    index_url = filing_index_url_from_master_filename(filename)
    html_url = primary_10k_html_url_from_index(index_url)

    if not html_url:
        print(f"[{base}] Could not find primary HTML on index page.")
        return

    url = normalize_sec_url(html_url)
    html = download(url)
    # Save raw html
    save_text(html, Path("data/raw_html") / f"{base}.htm")

    # Convert to text
    text = html_to_text(html)
    save_text(text, Path("data/text") / f"{base}.txt")
    # Extract Item 1C
    item_1c = extract_item_1c(text)
    if item_1c is None:
        print(f"[{base}] Item 1C not found.")
        return

    save_text(item_1c, Path("data/extracted") / f"{base}_item1c.txt")
    print(f"[{base}] Saved Item 1C.")


def main():
    df = load_master_idx(INDEX_URL)

    ten_ks = df[df["Form Type"] == "10-K"].copy()
    print("10-K count:", len(ten_ks))
    print(ten_ks.head())

    sample = ten_ks.sample(n=min(10, len(ten_ks)), random_state=42)
    sample.apply(process_filing, axis=1)


if __name__ == "__main__":
    main()
