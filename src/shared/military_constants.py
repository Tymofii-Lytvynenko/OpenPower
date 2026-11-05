UNIT_TRAINING_LEVELS = ("Recruit", "Regular", "Veteran", "Elite")

# Presentation metadata shared with content catalogs; combat policy stays in modules.
UNIT_ROLE_DOMAINS = {
    "infantry": "land", "infantry_vehicles": "land", "air_defense": "land",
    "mobile_launchers": "land", "tanks": "land", "artillery": "land",
    "attack_helicopters": "air", "transport_helicopters": "air", "fighters": "air",
    "attack_aircraft": "air", "bombers": "air", "anti_submarine_helicopters": "naval",
    "patrol_craft": "naval", "corvettes": "naval", "frigates": "naval",
    "destroyers": "naval", "attack_submarines": "naval",
    "ballistic_missile_submarines": "naval", "aircraft_carriers": "naval",
    "strategic_missiles": "strategic", "missile_defense": "strategic",
}


ROLE_ALIASES = {
    "army": "infantry",
    "infantry_vehicle": "infantry_vehicles",
    "infantry_vehicle_brigade": "infantry_vehicles",
    "artillery_gun": "artillery",
    "ifv": "infantry_vehicles",
    "apc": "infantry_vehicles",
    "air_defence": "air_defense",
    "mobile_launcher": "mobile_launchers",
    "tank": "tanks",
    "artillery_brigade": "artillery",
    "transport_helicopter": "transport_helicopters",
    "attack_helicopter": "attack_helicopters",
    "asw_helicopter": "anti_submarine_helicopters",
    "anti_submarine_helicopter": "anti_submarine_helicopters",
    "fighter_aircraft": "fighters",
    "fighter": "fighters",
    "bomber": "bombers",
    "patrol_boat": "patrol_craft",
    "corvette": "corvettes",
    "frigate": "frigates",
    "destroyer": "destroyers",
    "attack_submarine": "attack_submarines",
    "ballistic_missile_submarine": "ballistic_missile_submarines",
    "aircraft_carrier": "aircraft_carriers",
    "strategic_missile": "strategic_missiles",
    "ballistic_missile": "strategic_missiles",
}
