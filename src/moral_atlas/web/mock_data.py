"""Temporary API fixtures; replace behind the route layer when real data is ready."""

QUESTIONS = [
    {"id": "responsibility", "choices": [
        {"id": "a", "label": "Reckoning", "copy": "A leader causes real harm, then chooses public accountability even though it will cost the people who still believe in them."},
        {"id": "b", "label": "Repair", "copy": "The person harmed refuses an easy punishment and asks what it would take for everyone involved to make a life after the damage."},
    ]},
    {"id": "loyalty", "choices": [
        {"id": "a", "label": "Loyalty", "copy": "Two friends protect each other through a terrible mistake, knowing that telling the truth might end the only family either of them has."},
        {"id": "b", "label": "Truth", "copy": "A friend breaks a promise to expose a secret that could hurt someone else, and has to live with betraying the person they love."},
    ]},
    {"id": "rules", "choices": [
        {"id": "a", "label": "Order", "copy": "An outsider learns that the rules holding a small town together are cruel in places — but dismantling them may leave the vulnerable with nothing."},
        {"id": "b", "label": "Upheaval", "copy": "A young worker discovers that the system was designed to keep people like her out, and decides the only fair exception is a new system."},
    ]},
    {"id": "forgiveness", "choices": [
        {"id": "a", "label": "Second chance", "copy": "After prison, a father returns to the daughter he failed and tries to earn a place in her life without asking her to forgive him."},
        {"id": "b", "label": "Consequences", "copy": "A woman is asked to forgive the person who destroyed her family, and discovers that mercy is not the same thing as letting someone escape."},
    ]},
    {"id": "community", "choices": [
        {"id": "a", "label": "Inheritance", "copy": "An eldest child returns home to protect a fading family tradition, even as everyone else wants permission to become someone new."},
        {"id": "b", "label": "Freedom", "copy": "A tight-knit community starts to fracture when its youngest members ask whether belonging should ever require becoming the same."},
    ]},
]

COMPASS_PROFILE = {
    "varianceExplained": 71,
    "interpretation": "You sit where the old order is worth questioning and cruelty usually has a cause.",
    "position": {"x": 66, "y": 34},
    "points": [
        {"x": 8, "y": 88}, {"x": 12, "y": 82, "label": "The Lion King"}, {"x": 19, "y": 63},
        {"x": 29, "y": 39, "label": "Paddington 2"}, {"x": 36, "y": 69}, {"x": 46, "y": 49},
        {"x": 58, "y": 19}, {"x": 65, "y": 84}, {"x": 68, "y": 15, "label": "Spotlight", "align": "left"},
        {"x": 78, "y": 44}, {"x": 86, "y": 12}, {"x": 88, "y": 22, "label": "Maleficent", "align": "left"},
    ],
}

ONBOARDING_FILMS = [
    {
        "id": "the-lion-king-1994",
        "title": "The Lion King",
        "year": 1994,
        "genre": "Animation",
        "runtime_min": 88,
        "poster_tone": "lion-king",
    },
]
