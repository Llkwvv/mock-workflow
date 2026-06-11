"""Crawl jindata.sd.gov.cn catalog, download one file per directory, and generate configs."""

import json
import re
import time
from pathlib import Path

import requests

BASE_URL = "http://jindata.sd.gov.cn"
DOWNLOAD_DIR = Path("/home/lkw/usr_local_project/mock-workflow/mockworkflow-0.2/samples/jindata")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# Priority: xlsx > xls > sql > csv > json > rdf > xml > other
FORMAT_PRIORITY = {"xlsx": 1, "xls": 2, "sql": 3, "csv": 4, "json": 5, "rdf": 6, "xml": 7}


def extract_category_codes(html: str) -> dict:
    """Extract category codes from homepage HTML."""
    categories = {
        "org_code": [],
        "region_code": [],
    }

    # Extract region codes (区县)
    region_section = html.find('js-region-list')
    if region_section != -1:
        snippet = html[region_section:region_section+3000]
        items = re.findall(r'<li[^>]*data-code=["\']([^"\']+)["\'][^>]*>(.*?)</li>', snippet, re.DOTALL)
        for code, content in items:
            if code and code != 'qsydw' and re.match(r'^\d+$', code):
                text = re.sub(r'<[^>]+>', '', content).strip()
                count_match = re.search(r'\(([0-9]+)\)', text)
                count = int(count_match.group(1)) if count_match else 0
                categories["region_code"].append((code, count))

    # Extract org codes (市直部门 + 企事业单位)
    for section_name in ['js-organ-list', 'js-enterprise-list']:
        section_idx = html.find(section_name)
        if section_idx != -1:
            snippet = html[section_idx:section_idx+3000]
            items = re.findall(r'<li[^>]*data-code=["\']([^"\']+)["\'][^>]*>(.*?)</li>', snippet, re.DOTALL)
            for code, content in items:
                if code and code != 'qsydw':
                    text = re.sub(r'<[^>]+>', '', content).strip()
                    count_match = re.search(r'\(([0-9]+)\)', text)
                    count = int(count_match.group(1)) if count_match else 0
                    categories["org_code"].append((code, count))

    return categories


def fetch_uuids_for_category(session, filter_param: str, filter_code: str, expected_count: int = 0) -> dict:
    """Fetch all UUIDs for a single category."""
    uuids = {}
    page = 1
    empty_streak = 0

    while True:
        url = f"{BASE_URL}/jining/catalog/index?filterParam={filter_param}&filterParamCode={filter_code}&page={page}"
        try:
            r = session.get(url, timeout=15)
            r.raise_for_status()
        except Exception as e:
            print(f"    FAIL page {page}: {e}")
            break

        html = r.text
        matches = list(re.finditer(r'href=["\'](/jining/catalog/([a-f0-9]{32}))["\']', html))
        page_uuids = {}
        for m in matches:
            uuid = m.group(2)
            if uuid in page_uuids or uuid in uuids:
                continue
            idx = m.start()
            context = html[max(0, idx - 400) : min(len(html), idx + 300)]
            title_match = re.search(
                rf'<a[^>]*href=["\']{re.escape(m.group(1))}["\'][^>]*>([^<]+)</a>',
                context,
            )
            title = title_match.group(1).strip() if title_match else ""
            if title:
                page_uuids[uuid] = title

        if not page_uuids:
            empty_streak += 1
            if empty_streak >= 2:
                break
        else:
            empty_streak = 0
            uuids.update(page_uuids)

        if page % 10 == 0:
            print(f"    Fetched page {page} for {filter_code}, total: {len(uuids)}")

        page += 1
        time.sleep(0.3)

        # Safety break
        if page > 2000:
            print(f"    Safety break at page 2000 for {filter_code}")
            break

    return uuids


def fetch_catalog_uuids():
    """Fetch all catalog UUIDs by iterating through all categories."""
    uuids = {}
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    # Step 1: Fetch homepage to get category codes
    print("Fetching homepage to get category codes...")
    try:
        r = session.get(f"{BASE_URL}/jining/catalog/", timeout=15)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"FAIL to fetch homepage: {e}")
        return uuids

    categories = extract_category_codes(html)
    print(f"Found categories: {len(categories['org_code'])} org codes, {len(categories['region_code'])} region codes")

    # Step 2: Fetch org_code categories (市直部门 + 企事业单位)
    for code, count in categories["org_code"]:
        print(f"Fetching org_code={code} (expected ~{count})...")
        cat_uuids = fetch_uuids_for_category(session, "org_code", code, count)
        uuids.update(cat_uuids)
        print(f"  Got {len(cat_uuids)} UUIDs, total so far: {len(uuids)}")
        time.sleep(0.5)

    # Step 3: Fetch region_code categories (区县)
    for code, count in categories["region_code"]:
        print(f"Fetching region_code={code} (expected ~{count})...")
        cat_uuids = fetch_uuids_for_category(session, "region_code", code, count)
        uuids.update(cat_uuids)
        print(f"  Got {len(cat_uuids)} UUIDs, total so far: {len(uuids)}")
        time.sleep(0.5)

    print(f"Total catalogs found: {len(uuids)}")
    return uuids


def fetch_file_list(cata_id: str) -> list[dict]:
    """Fetch file list for a catalog."""
    url = f"{BASE_URL}/jining/catalog/getResourceWithFormat"
    params = {"cataId": cata_id, "pageNum": 1, "pageSize": 10, "fileFormat": ""}
    try:
        r = requests.get(url, params=params, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        if data.get("code") == 0 and data.get("object"):
            return data["object"].get("records", [])
    except Exception as e:
        print(f"    FAIL fetch files for {cata_id}: {e}")
    return []


def pick_best_file(files: list[dict]) -> dict | None:
    """Pick the best file based on format priority."""
    if not files:
        return None
    # Sort by priority
    scored = []
    for f in files:
        fmt = f.get("fileFormat", "").lower()
        priority = FORMAT_PRIORITY.get(fmt, 99)
        scored.append((priority, f))
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def download_file(file_info: dict, save_dir: Path) -> Path | None:
    """Download a single file."""
    id_in_rc = file_info.get("idInRc")
    file_name = file_info.get("fileDescription", "unknown")
    if not id_in_rc:
        return None

    url = f"{BASE_URL}/rcservice/docouter?docid={id_in_rc}&siteCode=370800000000"
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        safe_name = re.sub(r'[^\w\-.\u4e00-\u9fff]', '_', file_name)
        save_path = save_dir / safe_name
        save_path.write_bytes(r.content)
        return save_path
    except Exception as e:
        print(f"    FAIL download {file_name}: {e}")
    return None


def main():
    state_file = Path("/tmp/jindata_crawl_state.json")
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
    else:
        state = {"uuids": {}, "processed": [], "no_data": [], "failed": []}

    # Step 1: Fetch UUIDs if not already done or if count is too low
    current_uuids = state.get("uuids", {})
    if len(current_uuids) < 6000:
        print(f"Current UUIDs: {len(current_uuids)}, fetching all catalogs...")
        state["uuids"] = fetch_catalog_uuids()
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(f"Using cached {len(current_uuids)} UUIDs")

    uuids = state["uuids"]
    processed = set(state.get("processed", []))
    no_data = state.get("no_data", [])
    failed = state.get("failed", [])

    print(f"Processing {len(uuids)} catalogs...")

    for i, (uuid, title) in enumerate(uuids.items(), 1):
        if uuid in processed:
            continue

        print(f"[{i}/{len(uuids)}] {title[:30]} ({uuid})")
        files = fetch_file_list(uuid)
        best = pick_best_file(files)

        if best:
            print(f"    Best file: {best.get('fileDescription')} ({best.get('fileFormat')})")
            save_path = download_file(best, DOWNLOAD_DIR)
            if save_path:
                print(f"    Saved: {save_path}")
                processed.add(uuid)
            else:
                failed.append(uuid)
        else:
            print(f"    No files available")
            no_data.append(uuid)
            processed.add(uuid)

        if i % 20 == 0:
            state["processed"] = sorted(processed)
            state["no_data"] = no_data
            state["failed"] = failed
            state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        time.sleep(0.5)

    state["processed"] = sorted(processed)
    state["no_data"] = no_data
    state["failed"] = failed
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Done!")


if __name__ == "__main__":
    main()
