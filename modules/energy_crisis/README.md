# Energy Crisis Reference Mod

This module demonstrates the complete OpenPower extension path without importing
engine or server implementation details.

It contributes:

- a feature pack and one dependency-aware system;
- a module-owned action and durable domain event;
- a new world table and an extension of the countries schema;
- layered country data;
- a sequential save migration;
- a deterministic action scenario.

Validate and run it from the project root:

    openpower mod validate energy_crisis
    openpower sim run --mods energy_crisis --days 30 --seed 42 --player UKR --actions modules/energy_crisis/scenarios/policy_response.json
    openpower sim compare --mods energy_crisis --days 30 --seed 42 --player UKR --actions modules/energy_crisis/scenarios/policy_response.json
