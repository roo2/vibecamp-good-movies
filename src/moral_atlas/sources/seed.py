"""Seed the existing films table without fetching external evidence."""
from __future__ import annotations

import unicodedata

from .ingest import load_seeds, slugify
from .. import db


# Deliberately title-free, spoiler-light prompts for the blind story-pair stage.
# Keep these concrete and easy to scan: one situation, one choice, no more than
# about twenty words. They are read at 21px on a phone and should feel like a
# story someone can picture, not a miniature piece of film criticism.
DESCRIPTIONS = {
    "The Lion King": "A young leader must face his past and decide whether to save the home he left behind.",
    "Maleficent": "A feared outsider must decide whether pain from the past will rule her, or whether care can change her.",
    "The Lord of the Rings: The Return of the King": "Small companions carry a dangerous burden while leaders fight to protect a world without giving in to power.",
    "Hacksaw Ridge": "A soldier enters battle without a weapon and risks his life to save others while staying true to his beliefs.",
    "The Dark Knight": "A hero faces an enemy who uses fear and chaos to test whether good people will turn cruel.",
    "Frozen": "Two sisters kept apart by fear must learn whether love and honesty can bring their family back together.",
    "Joker": "A lonely man, ignored by his city, searches for respect as his pain turns into anger.",
    "Starship Troopers": "Young people join a proud army and begin to question what they were taught about duty and the enemy.",
    "Dead Poets Society": "A teacher urges his students to think for themselves, even when family and school demand obedience.",
    "Sleeping Beauty": "A sheltered young woman is caught between those who want to protect her and those who want revenge.",
    "Wicked": "Two unlikely friends must choose between staying loyal to each other and becoming who the world expects.",
    "The Wizard of Oz": "A lost girl travels with three companions who learn they may already have what they seek.",
    "Casablanca": "Two former lovers meet again and must choose between being together and helping a greater cause.",
    "It's a Wonderful Life": "A hopeless man is shown how much his ordinary life has mattered to the people around him.",
    "The Godfather": "A man joins the dangerous family business he once rejected and slowly changes what loyalty means.",
    "Thelma & Louise": "Two friends escape their old lives, but each step toward freedom leaves them fewer ways back.",
    "Groundhog Day": "A selfish man lives the same day again and again until he learns to care about others.",
    "Schindler's List": "A businessman inside a cruel system risks his wealth and safety to save the lives of strangers.",
    "Princess Mononoke": "A young warrior enters a fight between people and nature and searches for a way both can survive.",
    "Fight Club": "A lonely man finds purpose in a violent group, then sees that freedom can become another kind of control.",
    "The Matrix": "A man must choose between a comfortable lie and a dangerous truth.",
    "Billy Elliot": "A boy discovers a talent his family does not understand and must choose between fitting in and being himself.",
    "Gladiator": "A fallen leader is forced to fight for others while choosing between revenge and a better future.",
    "Spirited Away": "A girl trapped in a strange world must stay kind and remember who she is to save her family.",
    "Shrek": "A lonely outsider begins a rescue mission and learns that love and worth are not based on appearance.",
    "No Country for Old Men": "A man finds stolen money and is hunted through a world where violence seems impossible to escape.",
    "WALL-E": "A lonely robot finds love and tries to wake people from a comfortable life that is harming their world.",
    "The Wolf of Wall Street": "A young trader chases wealth and praise, ignoring the people harmed by his success.",
    "Arrival": "A language expert tries to understand unknown visitors and learns that love can matter even when loss is certain.",
    "Parasite": "A poor family enters the life of a rich family, building a plan that could easily fall apart.",
    "Sense and Sensibility": "Two sisters take different paths through love, balancing honest feelings against the need for safety.",
    "Pride & Prejudice": "Two people must look past pride and first impressions before they can understand each other.",
    "Top Gun: Maverick": "An ageing pilot trains a young team for a deadly mission while facing mistakes from his past.",
    "The Terminator": "A woman hunted by a machine discovers how strong she must become to protect the future.",
    "Zootopia": "A new police officer uncovers a plan that turns fear of difference against an entire city.",
    "Master and Commander: The Far Side of the World": "A sea captain chasing an enemy must weigh victory against friendship and the lives of his crew.",
    "Avatar": "A soldier sent to help take another people's home must choose which side he truly belongs to.",
    "The Avengers": "A group of powerful strangers must learn to trust each other before a shared enemy destroys their city.",
    "Guardians of the Galaxy": "A group of selfish outsiders must decide whether they will risk everything to protect people they barely know.",
    "Captain Marvel": "A soldier learns that her memories were changed and must decide who deserves her trust.",
    "Les Misérables": "A man given mercy tries to build a better life while a strict officer refuses to forgive his past.",
    "Bicycle Thieves": "A father and son search for a stolen bicycle that their family needs to survive.",
    "Rashomon": "Several people tell different stories about the same crime, making the truth hard to find.",
    "Tokyo Story": "An older couple visits their busy children and learns that love can remain even when families grow apart.",
    "Seven Samurai": "Poor villagers ask a group of warriors to defend them, and each must decide what another life is worth.",
    "A Man for All Seasons": "A public official risks his freedom and life rather than say something he believes is wrong.",
    "Chariots of Fire": "Two runners chase the same prize for different reasons while others try to control how they compete.",
    "Do the Right Thing": "A hot day pushes a neighbourhood's hidden anger into the open, forcing everyone to face their part in it.",
    "V for Vendetta": "A woman living under harsh rule joins a masked rebel and questions whether violence can create real freedom.",
    "A Separation": "A family dispute traps several people between honesty and duty, with every choice hurting someone.",
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


def sync_seed_films(path: str = "seeds/phase0.yaml") -> dict[str, int]:
    """Insert missing seed films and migrate curated descriptions in place.

    The film table is part research corpus and part product catalogue. Replacing
    a whole existing row here would erase fetched metadata and evidence links,
    so an existing film gets only its curated description updated. The operation
    is deliberately idempotent: deployments can run it every time code changes.
    """
    db.init_db()
    films = db.list_films()
    existing = {(film["title"], film.get("year")): film for film in films}
    existing_ids = {film["film_id"] for film in films}
    result = {"inserted": 0, "updated": 0, "unchanged": 0}
    for seed in load_seeds(path):
        key = (seed["title"], seed.get("year"))
        film_id = slugify(*key)
        description = _description_for(seed["title"])
        if key not in existing:
            if film_id in existing_ids:
                raise ValueError(
                    f"Refusing to replace existing film {film_id!r} while adding {key!r}"
                )
            db.upsert_film({
                "film_id": film_id,
                "title": seed["title"],
                "year": seed.get("year"),
                "seed_note": seed.get("note"),
                "description": description,
                "fetched_at": db.now(),
            })
            existing[key] = {"film_id": film_id, "description": description}
            existing_ids.add(film_id)
            result["inserted"] += 1
        elif existing[key].get("description") != description:
            # Use the stored id rather than deriving it: imported corpora may
            # preserve an older id convention even when title and year match.
            db.set_film_description(existing[key]["film_id"], description)
            existing[key]["description"] = description
            result["updated"] += 1
        else:
            result["unchanged"] += 1
    return result


def seed_films(path: str = "seeds/phase0.yaml") -> int:
    """Backward-compatible wrapper returning the number of missing films added."""
    return sync_seed_films(path)["inserted"]
