#!/usr/bin/env python3
"""Download every raw dataset Rock Match uses into backend/data/raw/.

Sources (all public):
  * NASA PDS Geosciences Node - MER APXS oxide bundle (Spirit + Opportunity)
  * NASA PDS Geosciences Node - MSL APXS RDR (Curiosity): concentration tables,
    per-measurement oxide files (*rwp*.csv) and X-ray spectra (*rsp*.csv)
  * Canadian Space Agency Open Data - APXS (Curiosity) mirror + lab calibration
    standards measured with the flight instrument (Open Government Licence - Canada)
  * NASA/JPL MMGIS - Curiosity waypoints and traverse
  * PDS Analyst's Notebook (WUSTL) - Spirit and Opportunity corrected traverses

The script is resumable: files that already exist are skipped.

Usage (from the repo root):
    python backend/scripts/fetch_data.py               # everything (~70 MB)
    python backend/scripts/fetch_data.py --no-spectra  # skip *rsp*.csv spectra (~5 MB)
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

# Certificate verification stays ON. The OS trust store (via `truststore`) is preferred
# because the CSA server sends an incomplete chain that only OS verifiers can complete.
try:
    import truststore
    SSL_CTX = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
except ImportError:  # pragma: no cover
    try:
        import certifi
        SSL_CTX = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        SSL_CTX = ssl.create_default_context()
CURL = shutil.which("curl")


def curl_get(url: str, timeout: int) -> bytes:
    """Fallback that uses the system curl (also verifies certificates)."""
    r = subprocess.run([CURL, "-fsSL", "--max-time", str(timeout), "-A", USER_AGENT, url],
                       capture_output=True, check=False)
    if r.returncode == 22:
        raise urllib.error.HTTPError(url, 404, "not found (curl)", {}, None)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed ({r.returncode}): {r.stderr.decode(errors='replace').strip()}")
    return r.stdout

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
USER_AGENT = "RockMatch-SpaceApps/1.0 (educational hackathon project)"

PDS_MSL = "https://pds-geosciences.wustl.edu/msl/msl-m-apxs-4_5-rdr-v1/mslapx_1xxx"
PDS_MER = "https://pds-geosciences.wustl.edu/mer/mer1_mer2-m-apxs-5-oxide-sci-v1"
CSA = "https://donnees-data.asc-csa.gc.ca/users/OpenData_DonneesOuvertes/pub/APXS"
CSA_PORTAL = "https://data.asc-csa.gc.ca/en/dataset/4596426-1c8f-3l9j-895mmct858mg42"
JPL_MSL = "https://mars.nasa.gov/mmgis-maps/MSL/Layers/json"
WUSTL_MER = "https://an.rsl.wustl.edu/mera/AN/meri/MER/traverse"
PDS_GRS = "https://pds-geosciences.wustl.edu/ody/ody-m-grs-5-elements-v1/odgm_xxxx"
GRS_MAPS = ("cl", "fe", "h2o", "k", "si", "th")


# --------------------------------------------------------------------------- http

def get(url: str, timeout: int = 90, tries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                raise
            err = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            err = e
            if CURL and isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                return curl_get(url, timeout)
        time.sleep(1.5 * 2 ** attempt)
    raise RuntimeError(f"failed after {tries} tries: {url} ({err})")


def save(url: str, dest: Path) -> str:
    """Download url to dest unless it already exists. Returns 'new', 'skip' or 'missing'."""
    if dest.exists() and dest.stat().st_size > 0:
        return "skip"
    try:
        data = get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "missing"
        raise
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return "new"


def listing(url: str) -> list[str]:
    """File/dir names in an Apache or IIS directory listing (dirs end with '/')."""
    if not url.endswith("/"):
        url += "/"
    page = get(url).decode("utf-8", "replace")
    base = urllib.parse.urlparse(url).path
    names = []
    for href in re.findall(r'href="([^"]+)"', page, flags=re.I):
        href = html.unescape(href)
        if href.startswith(("?", "#", "mailto:")) or "://" in href:
            continue
        path = urllib.parse.urlparse(urllib.parse.urljoin(url, href)).path
        if not path.startswith(base) or path == base:
            continue
        name = urllib.parse.unquote(path[len(base):])
        if name and "/" not in name.rstrip("/"):
            names.append(name)
    return sorted(set(names))


def download_many(jobs: list[tuple[str, Path]], label: str, workers: int) -> dict:
    stats = {"new": 0, "skip": 0, "missing": 0, "failed": 0}
    if not jobs:
        return stats
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(save, u, d): u for u, d in jobs}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            try:
                stats[fut.result()] += 1
            except Exception as e:  # keep going; report at the end
                stats["failed"] += 1
                print(f"  ! {futures[fut]}: {e}", file=sys.stderr)
            if i % 250 == 0 or i == len(jobs):
                print(f"  {label}: {i}/{len(jobs)}  ({stats['new']} new, {stats['skip']} cached, "
                      f"{stats['missing']} missing, {stats['failed']} failed, {time.time() - t0:.0f}s)", flush=True)
    return stats


def safe_extract(zip_path: Path, dest: Path) -> int:
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            name = Path(m.filename)
            if m.is_dir() or name.is_absolute() or ".." in name.parts:
                continue
            out = dest / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(m))
            n += 1
    return n


# --------------------------------------------------------------------------- steps

def fetch_mer(manifest: dict) -> None:
    print("\n[1/6] NASA PDS - MER APXS oxide bundle (Spirit + Opportunity)")
    d = RAW / "pds_mer_apxs"
    jobs = [(f"{PDS_MER}/mer_apxs_oxide.zip", d / "mer_apxs_oxide.zip")]
    for f in ("apxs_oxides_mer1.csv", "apxs_oxides_mer1.lbl", "apxs_oxides_mer2.csv", "apxs_oxides_mer2.lbl"):
        jobs.append((f"{PDS_MER}/merap_2xxx/data/{f}", d / f))
    s = download_many(jobs, "MER", 4)
    n = safe_extract(d / "mer_apxs_oxide.zip", d / "zip_contents")
    manifest["pds_mer_apxs"] = {"url": f"{PDS_MER}/", "license": "NASA PDS - public domain",
                                "files": len(jobs), "zip_members_extracted": n, **s}


def fetch_msl_tables(manifest: dict) -> None:
    print("\n[2/6] NASA PDS - MSL APXS concentration tables + index")
    d = RAW / "pds_msl_apxs"
    names = [n for n in listing(f"{PDS_MSL}/extras/") if n.endswith((".csv", ".txt"))]
    jobs = [(f"{PDS_MSL}/extras/{n}", d / "extras" / n) for n in names]
    jobs += [(f"{PDS_MSL}/index/{n}", d / "index" / n) for n in ("index.tab", "index.lbl")]
    jobs += [(f"{PDS_MSL}/{n}", d / n) for n in ("aareadme.txt", "errata.txt")]
    s = download_many(jobs, "MSL tables", 6)
    manifest["pds_msl_apxs_tables"] = {"url": f"{PDS_MSL}/extras/", "license": "NASA PDS - public domain",
                                       "files": len(jobs), **s}


def fetch_csa(manifest: dict, workers: int, spectra: bool) -> None:
    print("\n[3/6] Canadian Space Agency - APXS open data (calibration + Curiosity RDR mirror)")
    d = RAW / "csa_apxs"
    cal = f"{CSA}/Data/Calibration%20Data"
    jobs = [(f"{cal}/{urllib.parse.quote(n)}", d / "calibration" / n) for n in listing(cal + "/") if not n.endswith("/")]
    docs = f"{CSA}/Supporting%20Documents"
    jobs += [(f"{docs}/{urllib.parse.quote(n)}", d / "documents" / n) for n in listing(docs + "/") if not n.endswith("/")]
    rdr = f"{CSA}/Data/msl-m-apxs-4_5-rdr-v1"
    sols = [n for n in listing(rdr + "/") if re.fullmatch(r"sol\d{5}/", n)]
    print(f"  listing {len(sols)} sol folders on the CSA server ...", flush=True)

    def sol_jobs(sol_dir: str) -> list[tuple[str, Path]]:
        out = []
        for n in listing(f"{rdr}/{sol_dir}"):
            if n.endswith(".csv") and ("rwp" in n or (spectra and "rsp" in n)):
                out.append((f"{rdr}/{sol_dir}{n}", d / "rdr" / sol_dir.rstrip("/") / n))
        return out

    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for js in pool.map(sol_jobs, sols):
            jobs += js
    s = download_many(jobs, "CSA", workers)
    manifest["csa_apxs"] = {"url": CSA_PORTAL, "files_url": f"{CSA}/",
                            "license": "Open Government Licence - Canada",
                            "sol_folders": len(sols), "files": len(jobs), **s}


def fetch_msl_rdr(manifest: dict, workers: int, spectra: bool) -> None:
    print("\n[4/6] NASA PDS - MSL APXS per-measurement files (*rwp*.csv" + (" + *rsp*.csv)" if spectra else ")"))
    index = (RAW / "pds_msl_apxs" / "index" / "index.tab").read_text(errors="replace").splitlines()
    have_csa = {p.name for p in (RAW / "csa_apxs" / "rdr").rglob("*.csv")}
    jobs, from_csa, seen = [], 0, set()
    for line in index:
        cols = [c.strip().strip('"').strip() for c in line.split(",")]
        if len(cols) < 6 or cols[5] not in ("APXS_RWP", "APXS_RSP"):
            continue
        if cols[5] == "APXS_RSP" and not spectra:
            continue
        sol_dir = cols[1].lower().rstrip("/")
        name = cols[2].lower().replace(".lbl", ".csv")
        if name in seen:            # the PDS index lists each product more than once
            continue
        seen.add(name)
        if name in have_csa:
            from_csa += 1
            continue
        jobs.append((f"{PDS_MSL}/{sol_dir}/{name}", RAW / "pds_msl_apxs" / sol_dir / name))
    print(f"  {from_csa} files already provided by the CSA mirror; {len(jobs)} to fetch from PDS", flush=True)
    s = download_many(jobs, "PDS RDR", workers)
    manifest["pds_msl_apxs_rdr"] = {"url": f"{PDS_MSL}/data/", "license": "NASA PDS - public domain",
                                    "files": len(jobs), "provided_by_csa_mirror": from_csa, **s}


def fetch_traverses(manifest: dict) -> None:
    print("\n[5/6] NASA/JPL - Curiosity waypoints and traverse")
    d = RAW / "jpl_msl"
    jobs = [(f"{JPL_MSL}/{n}", d / n) for n in ("MSL_waypoints.json", "MSL_traverse.json")]
    s = download_many(jobs, "JPL", 2)
    manifest["jpl_msl_traverse"] = {"url": f"{JPL_MSL}/", "license": "NASA/JPL-Caltech public data", **s}

    print("\n[6/6] PDS Analyst's Notebook - Spirit and Opportunity corrected traverses")
    d = RAW / "wustl_mer_traverse"
    jobs = [(f"{WUSTL_MER}/{n}", d / n) for n in
            ("MERA_traverse.csv", "MERA_traverse.lbl", "MERB_traverse_5130.csv", "MERB_traverse_5130.lbl")]
    s = download_many(jobs, "MER traverse", 2)
    manifest["wustl_mer_traverse"] = {"url": "https://an.rsl.wustl.edu/mera/AN/pages/mer/mer_traverse.htm",
                                      "license": "NASA PDS Geosciences Node", **s}


def fetch_grs(manifest: dict) -> None:
    print("\n[7/7] NASA PDS - Mars Odyssey Gamma Ray Spectrometer element maps (5x5 deg, smoothed)")
    d = RAW / "pds_ody_grs"
    jobs = [(f"{PDS_GRS}/data/smoothed/{e}_sr_5x5.{ext}", d / f"{e}_sr_5x5.{ext}") for e in GRS_MAPS for ext in ("tab", "lbl")]
    jobs += [(f"{PDS_GRS}/aareadme.txt", d / "aareadme.txt"), (f"{PDS_GRS}/catalog/dataset.cat", d / "dataset.cat")]
    s = download_many(jobs, "GRS", 4)
    manifest["pds_ody_grs"] = {"url": f"{PDS_GRS}/", "license": "NASA PDS - public domain",
                               "citation": "Boynton et al. (2007), JGR 112, E12S99; ODY-M-GRS-5-ELEMENTS-V1.0", **s}


STEPS = {"mer": fetch_mer, "tables": fetch_msl_tables, "csa": None, "rdr": None, "traverses": fetch_traverses, "grs": fetch_grs}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-spectra", action="store_true", help="skip the MSL *rsp*.csv X-ray spectra")
    ap.add_argument("--workers", type=int, default=6, help="parallel downloads per server (default 6)")
    ap.add_argument("--only", choices=sorted(STEPS), help="run a single step, e.g. --only grs")
    args = ap.parse_args()
    spectra = not args.no_spectra
    RAW.mkdir(parents=True, exist_ok=True)
    manifest_path = RAW / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    t0 = time.time()

    run = lambda name: args.only in (None, name)  # noqa: E731
    if run("mer"):
        fetch_mer(manifest)
    if run("tables"):
        fetch_msl_tables(manifest)
    if run("csa"):
        fetch_csa(manifest, args.workers, spectra)
    if run("rdr"):
        fetch_msl_rdr(manifest, args.workers, spectra)
    if run("traverses"):
        fetch_traverses(manifest)
    if run("grs"):
        fetch_grs(manifest)

    manifest["_retrieved_utc"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    manifest_path.write_text(json.dumps(manifest, indent=2))
    total = sum(1 for p in RAW.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in RAW.rglob("*") if p.is_file())
    print(f"\nDone in {time.time() - t0:.0f}s: {total} files, {size / 1e6:.1f} MB in {RAW}")
    failed = sum(v.get("failed", 0) for v in manifest.values() if isinstance(v, dict))
    if failed:
        print(f"WARNING: {failed} downloads failed - re-run the script to retry them.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
