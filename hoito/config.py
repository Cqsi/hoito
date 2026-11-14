"""Settings, seed domains, regions and statuses. Facts here are only search hints: the agent must
confirm everything it tells the user from a fetched page."""
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MAX_TURNS = 8      # model choice lives in llm.py
SEARCH_TURNS = 4   # rounds of searching before the agent must submit

# Official sources searched by default. Region sites are added per case.
OFFICIAL = [
    "kela.fi",         # Kela: refunds, EHIC, eligibility
    "yths.fi",         # FSHS: student health service for higher-education students
    "116117.fi",       # Medical helpline (Päivystysapu)
    "infofinland.fi",  # Guides for internationals, in English
    "hus.fi",          # Helsinki University Hospital: emergency departments in Uusimaa
    "stm.fi",          # Ministry of Social Affairs and Health: national client fees
    "thl.fi",          # Finnish Institute for Health and Welfare
    "migri.fi",        # Residence status
    "suomi.fi",        # Public services portal
]

PRIVATE = ["mehilainen.fi", "terveystalo.com", "pihlajalinna.fi", "aava.fi"]

# City → wellbeing services county (the public healthcare provider). Domains confirmed indexed by Exa
# on 2026-11-14 (notes/exa-coverage.md).
REGIONS = {
    "Helsinki": {"county": "City of Helsinki (organises its own health services) + HUS for emergencies", "domains": ["hel.fi", "hus.fi"]},
    "Espoo": {"county": "Western Uusimaa wellbeing services county (Länsi-Uudenmaan hyvinvointialue)", "domains": ["luvn.fi", "hus.fi"]},
    "Vantaa": {"county": "Vantaa and Kerava wellbeing services county", "domains": ["vakehyva.fi", "hus.fi"]},
    "Kerava": {"county": "Vantaa and Kerava wellbeing services county", "domains": ["vakehyva.fi", "hus.fi"]},
    "Kauniainen": {"county": "Western Uusimaa wellbeing services county", "domains": ["luvn.fi", "hus.fi"]},
    "Tampere": {"county": "Pirkanmaa wellbeing services county (Pirha)", "domains": ["pirha.fi"]},
    "Turku": {"county": "Southwest Finland wellbeing services county (Varha)", "domains": ["varha.fi"]},
    "Oulu": {"county": "North Ostrobothnia wellbeing services county (Pohde)", "domains": ["pohde.fi"]},
    "Jyväskylä": {"county": "Central Finland wellbeing services county (Hyvaks)", "domains": ["hyvaks.fi"]},
    "Kuopio": {"county": "North Savo wellbeing services county", "domains": ["pshyvinvointialue.fi"]},
    "Lahti": {"county": "Päijät-Häme wellbeing services county", "domains": ["paijatha.fi"]},
    "Lappeenranta": {"county": "South Karelia wellbeing services county", "domains": ["ekhva.fi"]},
    "Joensuu": {"county": "North Karelia wellbeing services county (Siun sote)", "domains": ["siunsote.fi"]},
    "Vaasa": {"county": "Ostrobothnia wellbeing services county", "domains": ["osterbottensvalfard.fi"]},
    "Rovaniemi": {"county": "Lapland wellbeing services county", "domains": ["lapha.fi"]},
}

STATUSES = {
    "degree_student": "Degree student at a Finnish university or university of applied sciences",
    "exchange_student": "Exchange student (studying in Finland for a semester or a year)",
    "employee": "Employed in Finland (has an employer)",
    "resident": "Lives in Finland but is not working or studying (e.g. family member, job seeker)",
    "eu_visitor": "Visitor from an EU/EEA country or Switzerland (may have an EHIC card)",
    "non_eu_visitor": "Visitor from outside the EU (tourist, business trip, conference)",
}

# Where to look first for each status. Hints only; the agent checks each against sources.
STATUS_HINTS = {
    "degree_student": "Check FSHS (yths.fi) first; for evenings, weekends and emergencies check the regional emergency service and 116117.",
    "exchange_student": "Check whether exchange students can use FSHS (yths.fi) and what the regional public health centre charges them; also check Kela for EHIC rules if from the EU.",
    "employee": "For anything that is not an emergency, the main option is occupational health care (työterveyshuolto) arranged by the employer, during its opening hours; cite a page that explains it (InfoFinland, Kela, suomi.fi). Alternatives: the regional public health centre, private clinics with the Kela refund, and 116117 outside office hours.",
    "resident": "Check the regional public health centre and its fees; whether they have a Kela card affects private-care refunds.",
    "eu_visitor": "Check what an EHIC holder pays at a public health centre and emergency department (kela.fi, infofinland.fi, region site).",
    "non_eu_visitor": "Check what a non-resident pays in public emergency care (often the full cost) versus a private clinic visit price; travel insurance usually covers private clinics.",
}
