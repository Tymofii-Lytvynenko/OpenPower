RESOURCE_MAPPING = {
    # Raw Materials
    "cereals": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "vegetables_and_fruits": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "meat_and_fish": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "dairy": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "tobacco": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "drugs_and_raw_plants": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "other_food_and_beverages": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "wood_and_paper": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},
    "minerals": {"category": "Raw Materials", "unit": "USD", "base_price": 1.0},

    # Energy
    "fossil_fuels": {"category": "Energy", "unit": "USD", "base_price": 1.0},
    "electricity": {"category": "Energy", "unit": "USD", "base_price": 1.0},

    # Industrial Materials
    "iron_and_steel": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},
    "non_ferrous_metals": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},
    "precious_stones": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},
    "fabrics_and_leather": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},
    "plastics_and_rubber": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},
    "chemicals": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},
    "construction_materials": {"category": "Industrial Materials", "unit": "USD", "base_price": 1.0},

    # Finished Goods
    "pharmaceuticals": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},
    "appliances": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},
    "vehicles": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},
    "machinery_and_instruments": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},
    "commodities": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},
    "luxury_commodities": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},
    "arms_and_ammunition": {"category": "Finished Goods", "unit": "USD", "base_price": 1.0},

    # Services
    "transport_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "tourism_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "construction_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "financial_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "it_and_telecom_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "business_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "recreational_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "health_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "education_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "government_services": {"category": "Services", "unit": "USD", "base_price": 1.0},
    "industrial_services": {"category": "Services", "unit": "USD", "base_price": 1.0}
}

def get_resource_meta(res_id: str):
    return RESOURCE_MAPPING.get(res_id, {"category": "Unclassified", "unit": "units"})
