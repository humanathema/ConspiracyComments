"""Build a superset candidate list of maverick-authority figures from public
reference lists (whistleblowers, leakers, conspiracy theorists by topic,
HIV/AIDS denialists, anti-vaccine activists, pseudoarchaeology proponents),
then score each candidate by how often it's actually mentioned in the
21.4M-row r/conspiracy corpus using pyahocorasick (single O(n) pass
regardless of candidate-list size).

This is Stage 0 of the maverick_authority entity-curation task (see
ANTIGRAVITY_HANDOFF.md §10): candidate generation + corpus-frequency
triage. Final keep/cut decisions are Nash's call, not automated here —
output is a CSV with a blank `decision` column for manual review.

Source lists pulled 2026-07-13 from Wikipedia (List of whistleblowers,
List of FBI whistleblowers, Category:American conspiracy theorists [partial,
A-G alphabetically -- category has 200+ pages],
Category:John F. Kennedy conspiracy theorists,
Category:9/11 conspiracy theorists, Category:UFO conspiracy theorists,
Category:HIV/AIDS denialists, Category:American anti-vaccination activists,
Pseudoarchaeology (proponents section)).

Output: data/processed/maverick_candidate_entities_scored.csv
"""
import re
import time
from collections import defaultdict

import ahocorasick
import pandas as pd
import pyarrow.parquet as pq

CORPUS_PATH = "data/processed/empath_scores_full.parquet"
OUT_PATH = "data/processed/maverick_candidate_entities_scored.csv"

# ---------------------------------------------------------------------------
# Candidate names by source category. Multi-category membership is itself a
# signal (cross-referenced = more likely a genuine, recognizable authority
# figure rather than an obscure single-list entry).
# ---------------------------------------------------------------------------

WHISTLEBLOWER = [
    "Bartolome de las Casas", "Samuel Shaw", "Silas Soule", "Edmund Dene Morel",
    "Boris Bazhanov", "Herbert Yardley", "Smedley Butler", "Herbert von Bose",
    "Jan Karski", "John Paul Vann", "Peter Buxtun", "John White", "Daniel Ellsberg",
    "Frank Serpico", "Perry Fellwock", "Vladimir Bukovsky", "Martha Mitchell",
    "W. Mark Felt", "Mark Felt", "Deep Throat", "Stanley Adams", "A. Ernest Fitzgerald",
    "Henri Pezerat", "Karen Silkwood", "Gregory C. Minor", "Richard B. Hubbard",
    "Dale G. Bridenbaugh", "Frank Snepp", "Ralph McGehee", "Viktor Suvorov",
    "Clive Ponting", "John Michael Gravitt", "Duncan Edmonds", "Ingvar Bratt",
    "Cathy Massiter", "Ronald J. Goldstein", "Roger Wensil", "Mordechai Vanunu",
    "Joy Adams", "Howard Samuel Nunn", "Douglas Plumley", "Joseph Macktal",
    "Peter Wright", "Harry Templeton", "Roland Gibeault", "Michael Haddle",
    "Douglas D. Keeth", "William Schumer", "Myron Mehlman", "Vera English",
    "Arnold Gundersen", "Mark Whitacre", "Keith A. Schooley", "Linda Mitchell",
    "Sarah Thomas", "Erin Brockovich", "William Marcus", "Andre Cicolella",
    "William Sanjour", "Allen Mosbaugh", "Shannon Doyle", "George Galatis",
    "Jeffrey Wigand", "Allan Cutler", "David Franklin", "Timothy Kerr",
    "George D. Wynalda Jr.", "Michael Ruppert", "Juan Walterspiel", "Nancy Olivieri",
    "Frederic Whitehurst", "David Shayler", "David Shaylor", "Christoph Meili",
    "Alan Parkinson", "Shiv Chopra", "Paul van Buitenen", "Marc Hodler",
    "Linda Tripp", "Harry Markopolos", "Youri Bandazhevsky", "Marlene Garcia-Esperat",
    "Janet Howard", "Tanya Ward Jordan", "Joyce E. Megginson", "Karen Kwiatkowski",
    "Marsha Coleman-Adebayo", "Cynthia Cooper", "Sherron Watkins", "Coleen Rowley",
    "William Binney", "J. Kirke Wiebe", "Edward Loomis", "Sibel Edmonds",
    "Jeffrey Sterling", "Jeffrey Alexander Sterling", "Katharine Gun", "Joseph Wilson",
    "Neil Patrick Carrick", "Mukesh Kapila", "Samuel Provance", "Joe Darby",
    "Renee Dufault",
    # FBI whistleblowers list
    "William Tobin", "Jane Turner", "John Roberts", "Michael German",
    "Bassem Youssef", "Robert Kobus", "Darin Jones",
    # canonical leak-figures always cited by name
    "Julian Assange", "Chelsea Manning", "Bradley Manning", "Edward Snowden",
    "Seymour Hersh", "Michael Hastings", "Glenn Greenwald", "Barrett Brown",
    "Annie Machon", "Robert Baer", "Celerino Castillo", "Matt Taibbi",
    "George De Mohrenschildt", "WikiLeaks", "Project Veritas", "Aaron Swartz",
]

JFK_THEORIST = [
    "Jack Anderson", "Russ Baker", "Madeleine Duncan Brown", "Mae Brussell",
    "Milton William Cooper", "Roger D. Craig", "James DiEugenio", "Thomas N. Downing",
    "Michael Eddowes", "Billie Sol Estes", "James Fetzer", "Floyd Fithian",
    "Jim Garrison", "Dick Gregory", "G. Edward Griffin", "Robert J. Groden",
    "Bill Hicks", "Penn Jones Jr.", "Robert F. Kennedy Jr.", "Mark Lane",
    "David Lifton", "Jim Marrs", "Massimo Mazzucco", "Barr McClellan",
    "Robert Morrow", "Revilo P. Oliver", "Marguerite Oswald", "Michael Collins Piper",
    "L. Fletcher Prouty", "Jeff Rense", "Vincent Salandria", "Leo Sauvage",
    "Michael Shrimpton", "Richard E. Sprague", "Oliver Stone", "Roger Stone",
    "Jesse Ventura", "A. J. Weberman",
]

NINE_ELEVEN_THEORIST = [
    "Vanessa Beeley", "Richard Bergeron", "Mathias Brockers", "Michel Chossudovsky",
    "Jim Corr", "Elias Davidsson", "Daniele Ganser", "Philip Giraldi",
    "David Ray Griffin", "Alan Hart", "Jim Hoffman", "Barbara Honegger",
    "David Icke", "Steven E. Jones", "Cynthia McKinney", "John McMurtry",
    "Michael Meacher", "Thierry Meyssan", "Kenneth O'Keefe", "Steve Pieczenik",
    "Paul Craig Roberts", "William Rodriguez", "Michael Ruppert", "David Shayler",
    "Kurt Sonnenfeld", "Albert Stubblebine", "Webster Tarpley", "Lorie Van Auken",
    "Jesse Ventura", "Paul Joseph Watson", "L. Lin Wood", "Barrie Zwicker",
]

UFO_THEORIST = [
    "Stanton T. Friedman", "Linda Moulton Howe", "Bob Lazar", "John Lear",
    "Donald Keyhoe", "Jim Marrs", "David Icke", "Bill Moore", "Wilhelm Reich",
    "Giorgio Tsoukalos", "Haim Eshed",
]

CONSPIRACY_GENERAL = [
    "Seth Abramson", "Mike Adams", "Ali Alexander", "Gary Allen", "Steven Anderson",
    "Andrew Anglin", "Joe Arpaio", "Ed Asner", "Shiva Ayyadurai", "Roseanne Barr",
    "Norman G. Baker", "Kathy Barnette", "Del Bigtree", "Dan Bilzerian",
    "Max Blumenthal", "Robert Gregory Bowers", "Robert M. Bowman", "Matthew Bracken",
    "Kristen Breitweiser", "Kelly Brogan", "Ty Bollinger", "Rashid Buttar",
    "Patrick M. Byrne", "Christopher Cantwell", "Jack Cashill", "Danny Casolaro",
    "Tucker Carlson", "Jim Caviezel", "Mike Cernovich", "David Hatcher Childress",
    "Jerome Corsi", "Ann Coulter", "Thomas Cowan", "Dinesh D'Souza", "David Duke",
    "James Ellison", "Dave Emory", "F. William Engdahl", "James Fetzer",
    "Bryan Fischer", "Michael Flynn", "Nick Fuentes", "Tulsi Gabbard", "Matt Gaetz",
    "Frank Gaffney", "Ben Garrison", "Jim Garrison", "Pamela Geller", "Rudy Giuliani",
    "Louie Gohmert", "Simone Gold", "Naomi Wolf", "Robert David Steele",
    "Judy Mikovits", "Robert F. Kennedy Jr.", "Alex Jones", "David Icke",
]

HIV_AIDS_DENIALIST = [
    "Jad Adams", "Henry H. Bauer", "Tom Bethell", "Harvey Bialy",
    "Peter Duesberg", "Celia Farber", "G. Edward Griffin", "James P. Hogan",
    "Phillip E. Johnson", "Robert F. Kennedy Jr.", "Serge Lang", "Stefan Lanka",
    "Christine Maggiore", "Lynn Margulis", "Joseph Mercola", "Kary Mullis",
    "Gary Null", "David Rasnick", "Matthias Rath", "Robert Root-Bernstein",
    "Bret Weinstein",
]

ANTIVAX = [
    "Sharyl Attkisson", "Peter Breggin", "Dan Burton", "J. Bart Classen",
    "David Geier", "Mark Geier", "Richard E. Frye", "H. Hugh Fudenberg",
    "Boyd Haley", "Brian Hooker", "Sayer Ji", "Steve Kirsch", "Joseph Ladapo",
    "James Lyons-Weiler", "Robert W. Malone", "Jenny McCarthy", "Peter A. McCullough",
    "Judy Mikovits", "Mark Crispin Miller", "Christiane Northrup", "Bernard Rimland",
    "Stephanie Seneff", "Sherri Tenpenny", "Naomi Wolf", "David Avocado Wolfe",
    "Andrew Wakefield",
]

PSEUDOARCHAEOLOGY = [
    "Erich von Daniken", "Graham Hancock", "Peter Kolosimo", "Louis Pauwels",
    "Jacques Bergier", "Immanuel Velikovsky", "Zecharia Sitchin", "Scott Creighton",
    "Robert Bauval", "Charles Piazzi Smyth", "Ron Wyatt", "Maurice Cotterell",
    "Richard Cassaro", "Robert Schoch", "Giorgio Tsoukalos", "Barry Fell",
    "Michael Cremo", "David Hatcher Childress", "Ignatius Donnelly",
    "Augustus Le Plongeon", "James Churchward", "Helena Blavatsky",
]

# Second wave: sourced by working from theory -> named proponents/experts
# rather than name -> theory (Wikipedia "List of conspiracy theories" plus
# theory-specific category/article pages), pulled 2026-07-13.

MOON_LANDING_THEORIST = [
    "Bill Kaysing", "Bart Sibrel", "Mary Bennett", "David Percy", "Una Ronald",
]

CHEMTRAIL_THEORIST = [
    "Art Bell", "Richard Finke", "William Thomas", "Chris Bovey",
    "Dane Wigington", "Clifford Carnicom",
]

FLAT_EARTH = [
    "Shabtai Ambron", "Alfio Basile", "Elizabeth Lady Blount", "E. W. Bullinger",
    "Frank Cherry", "Orlando Ferguson", "Carl Froch", "Kron Gracie", "Mike Hughes",
    "Lord Jamar", "John Jasper", "Charles K. Johnson", "Yuri Loza", "Bryce Mitchell",
    "Branimir Nestorovic", "Tyler Owens", "Stew Peters", "Javi Poves",
    "Igor Prokopenko", "Samuel Rowbotham", "Mark Sargent", "Samuel Shenton",
    "Tila Tequila", "Wilbur Glenn Voliva", "Deacon White", "Mohammed Yusuf",
]

COVID_THEORIST = [
    "Alex Berenson", "Piers Corbyn", "Catherine Austin Fitts", "Pierre Kory",
    "Luc Montagnier", "Peter Navarro", "Vivek Ramaswamy", "Li-Meng Yan",
    "Michael Yeadon", "Russell Brand", "Heather Heying", "Stella Immanuel",
    "Lara Logan", "Naomi Seibt", "Kate Shemirani", "Charlie Ward",
    "America's Frontline Doctors", "Mikki Willis",
]

NEW_WORLD_ORDER_THEORIST = [
    "Adam Weishaupt", "Mark Dice",
]

MKULTRA = [
    "Victor Marchetti", "Sidney Gottlieb", "Donald Ewen Cameron",
]

QANON = [
    "Paul Furber", "Coleman Rogers", "Tracy Diaz", "Ron Watkins", "Jim Watkins",
    "Robert Cornero Jr.", "Jason Gelinas", "Austin Steinbart",
    "Timothy Charles Holmseth", "Martin Geddes",
]

GMO_THEORIST = [
    "Jeffrey M. Smith", "Marie-Monique Robin", "Vandana Shiva", "Tami Canal",
]

EPSTEIN_JOURNALIST = [
    "Julie K. Brown", "Vicky Ward", "Roger Sollenberger", "Whitney Webb",
]

# Third wave, prompted by Nash: (1) credentialed-professional advocacy
# organizations (AE911Truth-type groups -- these are the "platonic ideal" of
# maverick authority: a body of professionals collectively dissenting from
# an official account) and their named founders/leaders; (2) intelligent
# design movement (Discovery Institute) as another institutional-dissent
# archetype; (3) Joe Rogan Experience scientist guests, since Rogan is a
# major venue through which credentialed figures reach r/conspiracy-adjacent
# audiences; (4) remaining theory gaps: Bilderberg, Sandy Hook, fluoride,
# free-energy suppression.

CREDENTIALED_ADVOCACY_ORG = [
    "Architects & Engineers for 9/11 Truth", "AE911Truth", "Richard Gage",
    "Pilots for 9/11 Truth", "Firefighters for 9/11 Truth",
    "Lawyers for 9/11 Truth", "Scholars for 9/11 Truth",
    "Scientists for 9/11 Truth", "Political Leaders for 9/11 Truth",
    "Religious Leaders for 9/11 Truth", "Veterans for 9/11 Truth",
    "Kevin Barrett", "Discovery Institute", "Fluoride Action Network",
    "Front Line COVID-19 Critical Care Alliance", "FLCCC",
    "National Vaccine Information Center", "Physicians for Informed Consent",
]

INTELLIGENT_DESIGN = [
    "Michael Behe", "William Dembski", "Stephen C. Meyer", "Paul Nelson",
]

ROGAN_GUEST_SCIENTIST = [
    "Joe Rogan", "Brian Cox", "Sean Carroll", "Neil deGrasse Tyson",
    "Michio Kaku", "Avi Loeb", "William Happer", "Richard Dawkins",
    "Carole Hooven", "Andrew Huberman", "Rhonda Patrick", "Paul Stamets",
    "Garry Nolan",
]

BILDERBERG_THEORIST = [
    "Daniel Estulin", "Jim Tucker",
]

SANDY_HOOK_THEORIST = [
    "Wolfgang Halbig",
]

FREE_ENERGY_THEORIST = [
    "Nikola Tesla", "Stanley Meyer", "John Searl", "Bob Boyce", "Daniel Dingel",
]

CLIMATE_SKEPTIC_ORG = [
    "CO2 Coalition", "Global Warming Policy Foundation", "William Happer",
    "William O'Keefe", "John Clauser", "Patrick Michaels", "Gregory Wrightstone",
]

MISC_THEORIST = [
    "Jay Weidner",  # Georgia Guidestones
]

CATEGORY_LISTS = {
    "whistleblower": WHISTLEBLOWER,
    "jfk_theorist": JFK_THEORIST,
    "911_theorist": NINE_ELEVEN_THEORIST,
    "ufo_theorist": UFO_THEORIST,
    "conspiracy_general": CONSPIRACY_GENERAL,
    "hiv_aids_denialist": HIV_AIDS_DENIALIST,
    "antivax": ANTIVAX,
    "pseudoarchaeology": PSEUDOARCHAEOLOGY,
    "moon_landing_theorist": MOON_LANDING_THEORIST,
    "chemtrail_theorist": CHEMTRAIL_THEORIST,
    "flat_earth": FLAT_EARTH,
    "covid_theorist": COVID_THEORIST,
    "new_world_order_theorist": NEW_WORLD_ORDER_THEORIST,
    "mkultra": MKULTRA,
    "qanon": QANON,
    "gmo_theorist": GMO_THEORIST,
    "epstein_journalist": EPSTEIN_JOURNALIST,
    "credentialed_advocacy_org": CREDENTIALED_ADVOCACY_ORG,
    "intelligent_design": INTELLIGENT_DESIGN,
    "rogan_guest_scientist": ROGAN_GUEST_SCIENTIST,
    "bilderberg_theorist": BILDERBERG_THEORIST,
    "sandy_hook_theorist": SANDY_HOOK_THEORIST,
    "free_energy_theorist": FREE_ENERGY_THEORIST,
    "climate_skeptic_org": CLIMATE_SKEPTIC_ORG,
    "misc_theorist": MISC_THEORIST,
}

MIN_NAME_LEN = 5  # drop anything too short/ambiguous for substring matching


def normalize(name):
    return name.strip()


def build_candidates():
    cat_map = defaultdict(set)
    for cat, names in CATEGORY_LISTS.items():
        for n in names:
            n = normalize(n)
            if len(n) < MIN_NAME_LEN:
                continue
            cat_map[n].add(cat)
    rows = []
    for name, cats in cat_map.items():
        rows.append({
            "entity": name,
            "categories": ";".join(sorted(cats)),
            "n_categories": len(cats),
        })
    return pd.DataFrame(rows)


def build_automaton(names):
    A = ahocorasick.Automaton()
    for idx, name in enumerate(names):
        A.add_word(name.lower(), (idx, name))
    A.make_automaton()
    return A


WORD_CHAR = re.compile(r"\w")


def is_word_boundary_match(text, start, end):
    before_ok = start == 0 or not WORD_CHAR.match(text[start - 1])
    after_ok = end >= len(text) or not WORD_CHAR.match(text[end])
    return before_ok and after_ok


def scan_corpus(names, corpus_path, chunk_size=1_000_000):
    automaton = build_automaton(names)
    counts = defaultdict(int)
    pf = pq.ParquetFile(corpus_path)
    total = 0
    start_t = time.time()
    for i, batch in enumerate(pf.iter_batches(batch_size=chunk_size, columns=["id", "text"])):
        chunk = batch.to_pandas()
        total += len(chunk)
        for text in chunk["text"].fillna(""):
            text_l = text.lower()
            seen_this_row = set()
            for end_idx, (idx, name) in automaton.iter(text_l):
                start_idx = end_idx - len(name) + 1
                if is_word_boundary_match(text_l, start_idx, end_idx + 1):
                    seen_this_row.add(name)
            for name in seen_this_row:
                counts[name] += 1
        elapsed = time.time() - start_t
        print(f"  chunk {i+1}: {len(chunk):,} rows (cumulative {total:,}, "
              f"{elapsed/60:.1f} min elapsed)", flush=True)
    return counts, total


def main():
    cand_df = build_candidates()
    print(f"{len(cand_df)} unique candidate entities across "
          f"{len(CATEGORY_LISTS)} source categories")

    names = cand_df["entity"].tolist()
    print(f"\nScanning corpus ({corpus_note()}) for {len(names)} candidates "
          f"using Aho-Corasick (single pass)...")
    counts, total = scan_corpus(names, CORPUS_PATH)

    cand_df["corpus_mentions"] = cand_df["entity"].apply(lambda n: counts.get(n, 0))
    cand_df["decision"] = ""  # blank column for manual keep/cut/maybe review
    cand_df = cand_df.sort_values(
        ["corpus_mentions", "n_categories"], ascending=False
    ).reset_index(drop=True)

    cand_df.to_csv(OUT_PATH, index=False)
    print(f"\nSaved {len(cand_df)} scored candidates to {OUT_PATH}")
    print(f"\nTop 30 by corpus mentions:")
    print(cand_df.head(30).to_string(index=False))
    print(f"\n{(cand_df['corpus_mentions'] == 0).sum()} candidates with zero "
          f"corpus mentions (bottom of the sort, likely not worth reviewing)")


def corpus_note():
    return CORPUS_PATH


if __name__ == "__main__":
    main()
