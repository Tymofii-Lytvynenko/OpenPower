from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CreditEntry:
    role: str
    people: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CreditGroup:
    id: str
    name: str
    entries: tuple[CreditEntry, ...]


# The public Steam Edition credit listing supplies English names and roles; the GML
# semantic controls for Mathieu Lemay and the Nordic Games staff corroborate this roster.
# Source credit ordering is documented in docs/ui/reference/source_links.md.
REFERENCE_STEAM_CREDIT_GROUPS = (
    CreditGroup(
        "golemlabs",
        "GolemLabs",
        (
            CreditEntry("CEO", ("Jean-René Couture",)),
            CreditEntry("Director of Operations", ("Mathieu Tremblay",)),
            CreditEntry("Director of Marketing", ("Marie-Eve Bourdages",)),
            CreditEntry("Game Design", ("Jean-René Couture", "Sébastien Kerjean", "GolemLabs Team")),
            CreditEntry("2D Art", ("Adam Pilkington",)),
            CreditEntry("Animation", ("Marc Lepage",)),
            CreditEntry("Modeling", ("Steve Labrecque", "Dominic Paquet")),
            CreditEntry("Textures", ("Nathalie Marineau",)),
            CreditEntry(
                "Programmers",
                (
                    "Alain Bellehumeur",
                    "François Durand",
                    "Nicolas Hatier",
                    "Francis Jackson",
                    "Jonathan Mercier",
                    "Mathieu Lemay",
                    "Frédéric O'Reilly",
                    "Germain Sauvé",
                    "Mathieu Tremblay",
                ),
            ),
            CreditEntry(
                "Additional Help",
                ("Martin Choquette (Choq Soul)", "William duBois (BBR)", "David Shooner"),
            ),
            CreditEntry("Sound and Music", ("Eric Vigneault",)),
            CreditEntry("Sound Effects", ("Martin Plante",)),
            CreditEntry("Additional Credits Music", ("DJ Remz",)),
        ),
    ),
    CreditGroup(
        "nordic_games",
        "Nordic Games GmbH",
        (
            CreditEntry("Business & Product Development Director", ("Reinhard Pollice",)),
            CreditEntry("Nordic Games GmbH Management", ("Klemens Kreuzer", "Lars Wingefors")),
        ),
    ),
    CreditGroup(
        "dreamcatcher",
        "DreamCatcher",
        (
            CreditEntry("President and CEO", ("Richard Wah Kan",)),
            CreditEntry("DreamCatcher Europe, Managing Director", ("Olivier Pierre",)),
            CreditEntry("DreamCatcher Europe, Vice President and CFO", ("Roch Roustan",)),
            CreditEntry("VP Product Development and Acquisitions", ("Robert Stevenson",)),
            CreditEntry("Vice President Marketing", ("Marshall Zwicker",)),
            CreditEntry("Producer", ("Bill Mooney",)),
            CreditEntry("Additional Production", ("Mike Adams",)),
            CreditEntry("Product Manager (North America)", ("Brian Gladman",)),
            CreditEntry("Brand Manager (Europe)", ("Simon Vivien",)),
            CreditEntry("Marketing Director (Europe)", ("Mathieu Saint-Denis",)),
            CreditEntry("Marketing Creative Director", ("Desmond Oku",)),
            CreditEntry("Illustrations", ("Russell Challenger",)),
            CreditEntry("Graphics Management", ("James Meecham (Canada)", "Odile Mousseau (Europe)")),
            CreditEntry("PR Coordinator", ("Tara Reed",)),
            CreditEntry("Localization Production", ("Christine Gervillié", "Yann Tisseyre")),
            CreditEntry("QA Manager", ("Mike Adams",)),
            CreditEntry("QA Lead Tester", ("Chris Elliott",)),
            CreditEntry(
                "Testers (Functional)",
                (
                    "Adrian Miller",
                    "Chris Nesbitt",
                    "Ryan Gavel",
                    "Vasso T. Kontoulis",
                    "Daniel Torreblanca",
                    "Dan Dawang",
                    "Aldo Fazzari",
                    "Anthony Finelli",
                ),
            ),
            CreditEntry("Testers (Compatibility)", ("Enzyme Testing Labs",)),
        ),
    ),
)

# MobyGames publishes the URL with Eric Vigneault; the source GML exposes a separate text row.
# Supplemental source values are documented in docs/ui/reference/source_links.md.
REFERENCE_CREDIT_SUPPLEMENTAL_TEXT = {
    ("golemlabs", "Sound and Music"): "(www.multimediarts.net)",
    ("golemlabs", "Copyright"): "© GolemLabs 2004",
}
