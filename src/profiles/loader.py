from pathlib import Path
import yaml
from src.profiles.schema import CompanyProfileSchema

PROFILES_DIR = Path(__file__).parent / "configs"

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

    return CompanyProfileSchema(**data)

def load_all_profiles() -> list[CompanyProfileSchema]:
    profiles = []
    for yaml_file in PROFILES_DIR.glob("*.yaml"):
        profiles.append(load_profile(yaml_file))
    return profiles

