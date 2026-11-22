import json
import hashlib
from decimal import Decimal
from datetime import datetime
from pathlib import Path

def audit_file(filepath: Path):
    print(f"\n========================================================")
    print(f"AUDITING FILE: {filepath.name}")
    print(f"File size: {round(filepath.stat().st_size / 1024, 2)} KB")
    print(f"========================================================")
    
    with open(filepath, "r", encoding="utf-8") as f:
        content_str = f.read()
        bundle = json.loads(content_str)

    manifest = bundle.get("manifest", {})
    items = bundle.get("items", [])
    
    # 1. Manifest verification
    print("[1] MANIFEST CHECK:")
    print(f"  - format_version: {manifest.get('format_version')}")
    print(f"  - domain: {manifest.get('domain')}")
    print(f"  - item_count manifest: {manifest.get('item_count')}")
    print(f"  - actual items count: {len(items)}")
    
    # Check SHA256
    items_json = json.dumps(items, ensure_ascii=False, sort_keys=True)
    computed_hash = hashlib.sha256(items_json.encode("utf-8")).hexdigest()
    recorded_hash = manifest.get("sha256_checksum")
    hash_match = computed_hash == recorded_hash
    print(f"  - SHA256 match: {'PASS' if hash_match else 'FAIL'} ({computed_hash[:16]}...)")
    
    # 2. Detailed item validation against DB schema
    domain = manifest.get("domain")
    print(f"\n[2] DATABASE SCHEMA FIT CHECK ({domain.upper()}):")
    
    issues = []
    
    if domain == "awards":
        for idx, it in enumerate(items):
            # Required fields: reference, buyer_name, winner_name, amount_ttc, status, published_at
            ref = it.get("reference")
            if not ref or len(str(ref)) > 64:
                issues.append(f"Item #{idx}: invalid reference '{ref}' (len={len(str(ref)) if ref else 0}, max=64)")
            
            buyer_name = it.get("buyer_name")
            if not buyer_name or not str(buyer_name).strip():
                issues.append(f"Item #{idx}: missing buyer_name")
                
            winner_name = it.get("winner_name")
            if not winner_name or not str(winner_name).strip():
                issues.append(f"Item #{idx}: missing winner_name")
                
            amount = it.get("amount_ttc")
            try:
                dec = Decimal(str(amount))
                if dec < 0 or dec > Decimal("9999999999999.99"):
                    issues.append(f"Item #{idx}: out of range amount_ttc '{amount}'")
            except Exception as e:
                issues.append(f"Item #{idx}: invalid amount_ttc '{amount}': {e}")
                
            pub = it.get("published_at")
            try:
                datetime.fromisoformat(pub)
            except Exception as e:
                issues.append(f"Item #{idx}: unparseable published_at '{pub}': {e}")
                
    elif domain == "bdc":
        total_line_items = 0
        for idx, it in enumerate(items):
            pid = it.get("portal_id")
            if not pid or not isinstance(pid, int):
                issues.append(f"Item #{idx}: invalid portal_id '{pid}' (expected int)")
                
            ref = it.get("reference")
            if not ref or len(str(ref)) > 64:
                issues.append(f"Item #{idx}: invalid reference '{ref}' (len={len(str(ref)) if ref else 0}, max=64)")
                
            buyer_name = it.get("buyer_name")
            if not buyer_name:
                issues.append(f"Item #{idx}: missing buyer_name")
                
            title = it.get("title")
            if not title:
                issues.append(f"Item #{idx}: missing title")
                
            pub = it.get("published_at")
            try:
                datetime.fromisoformat(pub)
            except Exception as e:
                issues.append(f"Item #{idx}: unparseable published_at '{pub}': {e}")
                
            dl = it.get("deadline_at")
            try:
                datetime.fromisoformat(dl)
            except Exception as e:
                issues.append(f"Item #{idx}: unparseable deadline_at '{dl}': {e}")
                
            lines = it.get("line_items", [])
            total_line_items += len(lines)
            for lidx, line in enumerate(lines):
                if not line.get("designation"):
                    issues.append(f"Item #{idx} Line #{lidx}: missing designation")
                qty = line.get("quantity")
                try:
                    Decimal(str(qty))
                except Exception as e:
                    issues.append(f"Item #{idx} Line #{lidx}: invalid quantity '{qty}': {e}")

        print(f"  - Total line items audited: {total_line_items}")
        
    print(f"  - Total schema issues found: {len(issues)}")
    if issues:
        for iss in issues[:10]:
            print(f"    [!] {iss}")
        if len(issues) > 10:
            print(f"    ... and {len(issues) - 10} more.")
    else:
        print("  - ALL ITEMS PERFECTLY CONFORM TO POSTGRESQL SCHEMA!")

if __name__ == "__main__":
    p_awards = Path("data/offline_exports/export_awards_20261121_230825.json")
    p_bdc = Path("data/offline_exports/export_bdc_20261121_231237.json")
    if p_awards.exists():
        audit_file(p_awards)
    if p_bdc.exists():
        audit_file(p_bdc)
