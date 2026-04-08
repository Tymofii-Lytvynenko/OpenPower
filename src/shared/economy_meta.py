RESOURCE_MAPPING = {
    # Raw Materials
    "cereals": {"category": "Raw Materials", "unit": "tons"},
    "vegetables_and_fruits": {"category": "Raw Materials", "unit": "tons"},
    "meat_and_fish": {"category": "Raw Materials", "unit": "tons"},
    "dairy": {"category": "Raw Materials", "unit": "tons"},
    "tobacco": {"category": "Raw Materials", "unit": "tons"},
    "drugs_and_raw_plants": {"category": "Raw Materials", "unit": "tons"},
    "other_food_and_beverages": {"category": "Raw Materials", "unit": "tons"},
    "wood_and_paper": {"category": "Raw Materials", "unit": "tons"},
    "minerals": {"category": "Raw Materials", "unit": "tons"},

    # Energy
    "fossil_fuels": {"category": "Energy", "unit": "tons"},
    "electricity": {"category": "Energy", "unit": "MW"},

    # Industrial Materials
    "iron_and_steel": {"category": "Industrial Materials", "unit": "tons"},
    "non_ferrous_metals": {"category": "Industrial Materials", "unit": "tons"},
    "precious_stones": {"category": "Industrial Materials", "unit": "tons"},
    "fabrics_and_leather": {"category": "Industrial Materials", "unit": "tons"},
    "plastics_and_rubber": {"category": "Industrial Materials", "unit": "tons"},
    "chemicals": {"category": "Industrial Materials", "unit": "tons"},
    "construction_materials": {"category": "Industrial Materials", "unit": "tons"},

    # Finished Goods
    "pharmaceuticals": {"category": "Finished Goods", "unit": "tons"},
    "appliances": {"category": "Finished Goods", "unit": "tons"},
    "vehicles": {"category": "Finished Goods", "unit": "tons"},
    "machinery_and_instruments": {"category": "Finished Goods", "unit": "tons"},
    "commodities": {"category": "Finished Goods", "unit": "tons"},
    "luxury_commodities": {"category": "Finished Goods", "unit": "tons"},
    "arms_and_ammunition": {"category": "Finished Goods", "unit": "tons"},

    # Services
    "transport_services": {"category": "Services", "unit": "man hours"},
    "tourism_services": {"category": "Services", "unit": "man hours"},
    "construction_services": {"category": "Services", "unit": "man hours"},
    "financial_services": {"category": "Services", "unit": "man hours"},
    "it_and_telecom_services": {"category": "Services", "unit": "man hours"},
    "business_services": {"category": "Services", "unit": "man hours"},
    "recreational_services": {"category": "Services", "unit": "man hours"},
    "health_services": {"category": "Services", "unit": "man hours"},
    "education_services": {"category": "Services", "unit": "man hours"},
    "government_services": {"category": "Services", "unit": "man hours"},
    "industrial_services": {"category": "Services", "unit": "man hours"}
}

def get_resource_meta(res_id: str):
    return RESOURCE_MAPPING.get(res_id, {"category": "Unclassified", "unit": "units"})
