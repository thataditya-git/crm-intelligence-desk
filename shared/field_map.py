FIELD_MAP = {
    "phone": "phone",
    "jobtitle": "jobtitle",
    "company": "company",
    "firstname": "firstname",
    "lastname": "lastname",
    "email": "email",
}


def to_hubspot_property(field_name: str) -> str:
    return FIELD_MAP.get(field_name, field_name)


def build_hubspot_properties(updates: dict) -> dict:
    return {to_hubspot_property(k): v for k, v in updates.items() if v is not None}
