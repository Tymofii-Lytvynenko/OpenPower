RESOURCE_MAPPING = {
    # Raw Materials
    "cereals": {"category": "Raw Materials", "unit": "tons", "base_price": 400.0},
    "vegetables_and_fruits": {"category": "Raw Materials", "unit": "tons", "base_price": 800.0},
    "meat_and_fish": {"category": "Raw Materials", "unit": "tons", "base_price": 3500.0},
    "dairy": {"category": "Raw Materials", "unit": "tons", "base_price": 2000.0},
    "tobacco": {"category": "Raw Materials", "unit": "tons", "base_price": 4500.0},
    "drugs_and_raw_plants": {"category": "Raw Materials", "unit": "tons", "base_price": 1500.0},
    "other_food_and_beverages": {"category": "Raw Materials", "unit": "tons", "base_price": 1200.0},
    "wood_and_paper": {"category": "Raw Materials", "unit": "tons", "base_price": 600.0},
    "minerals": {"category": "Raw Materials", "unit": "tons", "base_price": 300.0},

    # Energy
    "fossil_fuels": {"category": "Energy", "unit": "tons", "base_price": 150.0},
    "electricity": {"category": "Energy", "unit": "MW", "base_price": 80.0},

    # Industrial Materials
    "iron_and_steel": {"category": "Industrial Materials", "unit": "tons", "base_price": 700.0},
    "non_ferrous_metals": {"category": "Industrial Materials", "unit": "tons", "base_price": 2500.0},
    "precious_stones": {"category": "Industrial Materials", "unit": "tons", "base_price": 35000.0},
    "fabrics_and_leather": {"category": "Industrial Materials", "unit": "tons", "base_price": 3500.0},
    "plastics_and_rubber": {"category": "Industrial Materials", "unit": "tons", "base_price": 2000.0},
    "chemicals": {"category": "Industrial Materials", "unit": "tons", "base_price": 1200.0},
    "construction_materials": {"category": "Industrial Materials", "unit": "tons", "base_price": 150.0},

    # Finished Goods
    "pharmaceuticals": {"category": "Finished Goods", "unit": "tons", "base_price": 25000.0},
    "appliances": {"category": "Finished Goods", "unit": "tons", "base_price": 8500.0},
    "vehicles": {"category": "Finished Goods", "unit": "tons", "base_price": 5000.0},
    "machinery_and_instruments": {"category": "Finished Goods", "unit": "tons", "base_price": 12000.0},
    "commodities": {"category": "Finished Goods", "unit": "tons", "base_price": 5000.0},
    "luxury_commodities": {"category": "Finished Goods", "unit": "tons", "base_price": 15000.0},
    "arms_and_ammunition": {"category": "Finished Goods", "unit": "tons", "base_price": 12000.0},

    # Services
    "transport_services": {"category": "Services", "unit": "man hours", "base_price": 45.0},
    "tourism_services": {"category": "Services", "unit": "man hours", "base_price": 60.0},
    "construction_services": {"category": "Services", "unit": "man hours", "base_price": 55.0},
    "financial_services": {"category": "Services", "unit": "man hours", "base_price": 85.0},
    "it_and_telecom_services": {"category": "Services", "unit": "man hours", "base_price": 95.0},
    "business_services": {"category": "Services", "unit": "man hours", "base_price": 75.0},
    "recreational_services": {"category": "Services", "unit": "man hours", "base_price": 40.0},
    "health_services": {"category": "Services", "unit": "man hours", "base_price": 120.0},
    "education_services": {"category": "Services", "unit": "man hours", "base_price": 65.0},
    "government_services": {"category": "Services", "unit": "man hours", "base_price": 50.0},
    "industrial_services": {"category": "Services", "unit": "man hours", "base_price": 70.0}
}

def get_resource_meta(res_id: str):
    return RESOURCE_MAPPING.get(res_id, {"category": "Unclassified", "unit": "units"})
