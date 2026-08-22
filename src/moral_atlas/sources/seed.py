"""Seed the existing films table without fetching external evidence."""
from __future__ import annotations

import unicodedata

from .ingest import load_seeds, slugify
from .. import db


# Deliberately title-free, spoiler-free prompts for the blind story-pair stage.
DESCRIPTIONS = {
    "The Lion King": "A reluctant heir must decide whether returning to a troubled home is worth facing an old failure.",
    "Maleficent": "A feared outsider revisits the betrayal that shaped her and discovers care in an unexpected bond.",
    "The Lord of the Rings: The Return of the King": "Ordinary companions carry a burden through a collapsing world while leaders decide what power is for.",
    "Hacksaw Ridge": "A man enters a brutal institution determined to serve others without abandoning the principle that defines him.",
    "The Dark Knight": "A protector faces an enemy who believes fear can reveal what every decent person is really willing to do.",
    "Frozen": "Two sisters must choose between a safe distance and the difficult honesty required to repair a family bond.",
    "Joker": "An isolated man searches for dignity in a city that repeatedly treats suffering as someone else’s problem.",
    "Starship Troopers": "Young citizens join a vast military project and slowly confront the stories a society tells about duty and enemies.",
    "Dead Poets Society": "Students encounter a teacher who asks them to value their own voices inside a world built on expectation.",
    "Sleeping Beauty": "A sheltered young person becomes the focus of a conflict between protection, freedom, and old promises.",
    "Wicked": "Two unlikely friends navigate a public story that turns difference into danger and loyalty into a costly choice.",
    "The Wizard of Oz": "A young traveller crosses a strange land with companions who each believe they are missing what matters most.",
    "Casablanca": "Two people meet again in a place where private love and a larger struggle both demand a sacrifice.",
    "It's a Wonderful Life": "A discouraged man is forced to reconsider whether a life of small obligations has mattered to anyone else.",
    "The Godfather": "A family’s desire for security draws a reluctant heir into choices that change what belonging means.",
    "Thelma & Louise": "Two friends leave ordinary life behind and discover how freedom can become both thrilling and dangerously narrow.",
    "Groundhog Day": "A self-absorbed person is given repeated chances to ask whether change is real when no one is watching.",
    "Schindler's List": "A businessman living within a cruel system must decide how far personal influence can be used to protect others.",
    "Princess Mononoke": "People and forces of nature clash as a visitor tries to understand whether survival must always create enemies.",
    "Fight Club": "A dissatisfied man finds belonging in a secret movement that promises freedom while demanding a new kind of obedience.",
    "The Matrix": "An ordinary worker is offered a terrifying explanation for the world and must choose comfort or a difficult awakening.",
    "Billy Elliot": "A young person discovers a calling that challenges the role his family and community have prepared for him.",
    "Gladiator": "A respected leader loses everything and is drawn into a public struggle over revenge, honour, and the future of a nation.",
    "Spirited Away": "A child in an unfamiliar world learns to hold onto compassion and identity amid rules she does not understand.",
    "Shrek": "A solitary outsider’s quiet life is interrupted by a quest that challenges his assumptions about beauty and belonging.",
    "No Country for Old Men": "A chance discovery pulls several people into a pursuit where chance, violence, and moral certainty seem increasingly unstable.",
    "WALL-E": "A lonely caretaker discovers connection and asks a comfortable society to remember what responsibility to a shared world requires.",
    "The Wolf of Wall Street": "An ambitious newcomer embraces a culture of excess and must decide whether success excuses the damage left behind.",
    "Arrival": "A specialist confronting the unknown learns that understanding another perspective may change how a life is valued.",
    "Parasite": "Two families from sharply different circumstances become entangled in a fragile arrangement shaped by need and status.",
    "Sense and Sensibility": "Two sisters with opposite ideas about feeling and restraint each weigh what security is worth surrendering for.",
    "Pride & Prejudice": "Two people whose first judgements of each other prove wrong must weigh pride, station, and the cost of admitting a mistake.",
    "Top Gun: Maverick": "A veteran with a long record of disobedience is asked to prepare others for something he believes he should face himself.",
    "The Terminator": "An ordinary person is hunted by something implacable and discovers what she is willing to become in order to survive.",
    "Zootopia": "A newcomer determined to prove herself uncovers how readily a city turns fear of difference into policy.",
    "Master and Commander: The Far Side of the World": "A commander pursuing an enemy across the sea weighs duty, friendship, and the lives of the men who trust him.",
    "Avatar": "An outsider sent among a people he was meant to help displace must choose between the world that made him and the one that accepted him.",
    "The Avengers": "Powerful individuals who distrust one another must decide whether a shared threat is worth surrendering their independence for.",
    "Guardians of the Galaxy": "A band of self-interested outcasts find that protecting something larger than themselves costs more than they meant to give.",
    "Captain Marvel": "A soldier who has been told what she is discovers her memories were shaped by the people who trained her.",
}


def _description_for(title: str) -> str:
    candidates = [unicodedata.normalize("NFC", title)]
    try:
        candidates.append(unicodedata.normalize("NFC", title.encode("latin-1").decode("utf-8")))
    except UnicodeError:
        pass
    for known_title, description in DESCRIPTIONS.items():
        if unicodedata.normalize("NFC", known_title) in candidates:
            return description
    raise KeyError(f"No blind-story description seeded for {title!r}")


def seed_films(path: str = "seeds/phase0.yaml") -> int:
    """Insert missing seed films; never overwrite an existing film row."""
    db.init_db()
    existing = {(film["title"], film.get("year")) for film in db.list_films()}
    inserted = 0
    for seed in load_seeds(path):
        key = (seed["title"], seed.get("year"))
        film_id = slugify(*key)
        if key not in existing:
            db.upsert_film({
                "film_id": film_id,
                "title": seed["title"],
                "year": seed.get("year"),
                "seed_note": seed.get("note"),
                "description": _description_for(seed["title"]),
                "fetched_at": db.now(),
            })
            existing.add(key)
            inserted += 1
        else:
            db.set_film_description(film_id, _description_for(seed["title"]))
    return inserted
