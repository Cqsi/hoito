"""Red-flag check. Plain code, not the model: if any of these appear, the app says "Call 112" first."""
import re

# English, Finnish and Swedish phrasings of symptoms where the emergency number is the right first step.
RED_FLAGS = {
    "chest pain": r"chest (pain|pressure|tightness)|rintakipu|kipua rinnassa|bröstsmärta",
    "trouble breathing": r"(can'?t|cannot|hard to|difficulty|trouble|struggling to) breath|short(ness)? of breath|hengenahdistus|en saa henkeä|andnöd",
    "stroke signs": r"face (droop|drooping)|slurred speech|one side (of my|of the)? ?(body|face)|arm weakness|halvaus|aivoinfarkti|stroke",
    "unconscious": r"unconscious|passed out and|not waking|unresponsive|tajuton|medvetslös",
    "severe bleeding": r"(heavy|severe|won'?t stop|uncontrolled) bleeding|bleeding (heavily|a lot)|runsas verenvuoto",
    "severe allergic reaction": r"anaphyla|throat (is )?(swelling|closing)|lips swelling|kurkku turpoaa",
    "seizure": r"seizure|convuls|kouristus|kramp",
    "suicidal thoughts": r"suicid|kill myself|end my life|itsemurha|haluan kuolla|självmord",
    "overdose or poisoning": r"overdos|poison|myrkytys|yliannostus",
    "bleeding in pregnancy": r"pregnan.{0,60}bleed|bleed.{0,60}pregnan|raskau.{0,60}vuoto|vuoto.{0,60}raskau",
    "high fever in a baby": r"(baby|infant|newborn).{0,40}fever|fever.{0,40}(baby|infant|newborn)",
}

_COMPILED = {name: re.compile(p, re.I) for name, p in RED_FLAGS.items()}


def red_flags(text: str) -> list[str]:
    return [name for name, rx in _COMPILED.items() if rx.search(text or "")]
