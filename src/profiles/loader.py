from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from src.profiles.schema import CompanyProfileSchema

PROFILES_DIR = Path(__file__).parent / "configs"

DEFAULT_SECTOR_ICONS: Dict[str, str] = {
    "it_hardware": "🖥️",
    "software_data": "💻",
    "cctv_security": "📹",
    "btp_construction": "🏗️",
    "electricite_fluides": "⚡",
    "medical_pharma": "🏥",
    "transport_vehicules": "🚚",
    "nettoyage_gardiennage": "🧹",
    "bureau_mobilier": "📑",
    "etudes_conseil": "📊",
    "communication_event": "📢"
}

def load_profile(profile_path: Path | str) -> CompanyProfileSchema:
    path = Path(profile_path)
    if not path.is_absolute():
        path = PROFILES_DIR / path
        if not path.suffix:
            path = path.with_suffix(".yaml")

    if not path.exists():
        raise FileNotFoundError(f"Profile configuration not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    prof = CompanyProfileSchema(**data)
    slug = path.stem
    prof.profile_id = slug
    if not prof.icon:
        prof.icon = DEFAULT_SECTOR_ICONS.get(slug, "🏷️")
    return prof

def load_all_profiles() -> list[CompanyProfileSchema]:
    profiles = []
    # Preferred display order
    order = [
        "it_hardware", "software_data", "cctv_security", "btp_construction",
        "electricite_fluides", "medical_pharma", "transport_vehicules",
        "nettoyage_gardiennage", "bureau_mobilier", "etudes_conseil", "communication_event"
    ]
    seen = set()
    for slug in order:
        p_path = PROFILES_DIR / f"{slug}.yaml"
        if p_path.exists():
            profiles.append(load_profile(p_path))
            seen.add(p_path.name)

    # Any other custom profiles
    for yaml_file in sorted(PROFILES_DIR.glob("*.yaml")):
        if yaml_file.name not in seen:
            profiles.append(load_profile(yaml_file))
    return profiles

def save_profile(profile_data: Dict[str, Any], slug: str) -> CompanyProfileSchema:
    """Saves or updates a sector profile YAML file on disk"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    clean_slug = slug.strip().lower().replace(" ", "_")
    target_path = PROFILES_DIR / f"{clean_slug}.yaml"

    # Validate against schema
    validated = CompanyProfileSchema(**profile_data)
    validated.profile_id = clean_slug
    if not validated.icon:
        validated.icon = DEFAULT_SECTOR_ICONS.get(clean_slug, "🏷️")

    # Serialize to clean YAML
    dump_dict = validated.model_dump(exclude={"profile_id"}, exclude_none=True)
    with open(target_path, "w", encoding="utf-8") as f:
        yaml.dump(dump_dict, f, allow_unicode=True, sort_keys=False)

    return validated

def delete_profile(slug: str) -> bool:
    """Deletes a custom profile configuration file"""
    clean_slug = slug.strip().lower()
    target_path = PROFILES_DIR / f"{clean_slug}.yaml"
    if target_path.exists():
        target_path.unlink()
        return True
    return False

