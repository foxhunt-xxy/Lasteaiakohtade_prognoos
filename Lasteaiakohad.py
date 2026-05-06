import io
import re
import math
import time

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from pathlib import Path
OUTPUT_DIR = Path("Outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# =========================================================
# SEADED
# =========================================================

# Statistikaameti API baas-URL.
# Kõik järgnevad tabelite lingid ehitatakse selle peale.
BASE_URL = "https://andmed.stat.ee/api/v1/et/stat"


# ---------------------------------------------------------
# STATISTIKAAMETI TABELITE URL-id
# ---------------------------------------------------------

# Rahvastik soo, vanuse ja elukoha järgi
TABLE_POP = f"{BASE_URL}/RV0240"

# Elussündinud soo ja haldusüksuse järgi
TABLE_BIRTHS = f"{BASE_URL}/RV112U"

# Surnud soo ja haldusüksuse järgi
TABLE_DEATHS = f"{BASE_URL}/RV49U"

# Vanusepõhised sündimuskordajad (ASFR = Age Specific Fertility Rate)
TABLE_ASFR = f"{BASE_URL}/RV172"

# Rändesaldo haldusüksuse järgi
TABLE_MIG_MUNI = f"{BASE_URL}/RVR02"

# Rändesaldo vanuserühma järgi
TABLE_MIG_AGE = f"{BASE_URL}/RVR03"


# ---------------------------------------------------------
# ANALÜÜSITAV OMAVALITSUS
# ---------------------------------------------------------

# Vald või omavalitsus, mille kohta prognoosi tehakse
MUNICIPALITY_LABEL = "Rakvere vald"


# ---------------------------------------------------------
# AJAPERIOODID
# ---------------------------------------------------------

# Ajaloolised rahvastikuandmed aastatest 2015–2025
POP_HISTORY_YEARS = list(range(2015, 2026))

# Aastad, mille põhjal kasutatakse rändeandmeid
MIG_HISTORY_YEARS = [2022, 2023, 2024]

# Prognoosi aastad kuni 2035
FORECAST_YEARS = list(range(2026, 2036))

# Lasteaia kohtade prognoosi aastad
KINDER_YEARS = list(range(2026, 2031))


# ---------------------------------------------------------
# DEMOGRAAFILISED EELDUSED
# ---------------------------------------------------------

# Eesmärgiks seatud summaarne sündimuskordaja aastaks 2050
# (TFR = Total Fertility Rate)
TFR_TARGET_2050 = 1.63


# ---------------------------------------------------------
# LASTEAIAKOHTADE ANDMED
# ---------------------------------------------------------

# Kokku lasteaiakohti
TOTAL_KINDER_PLACES = 204

# Sõimekohtade arv (1.5–3 aastastele)
PLACES_15_TO_3 = 84


# ---------------------------------------------------------
# LASTEAIAS OSALEMISE MÄÄRAD VANUSE KAUPA
# ---------------------------------------------------------

# Näitab, kui suur osa vastava vanuse lastest käib lasteaias.
# Näiteks:
# 2-aastastest käib lasteaias hinnanguliselt 75%.
PARTICIPATION_BY_AGE = {
    1: 0.20,
    2: 0.75,
    3: 0.95,
    4: 0.97,
    5: 0.97,
    6: 0.97,
}


# ---------------------------------------------------------
# VANUSERÜHMAD
# ---------------------------------------------------------

# Kõik lasteaiaealised vanused
ALL_KINDER_AGES = [1, 2, 3, 4, 5, 6]

# Väikelaste vanused (sõimerühm)
SMALL_CHILD_AGES = [1, 2]

# Viljakas eas naiste vanused
FERTILE_AGES = list(range(15, 50))


# ---------------------------------------------------------
# ASFR VANUSERÜHMAD
# ---------------------------------------------------------

# Vanusegrupid sündimuskordajate jaoks.
# Kasutatakse sündide prognoosimisel.
ASFR_GROUPS = {
    "15-19": list(range(15, 20)),
    "20-24": list(range(20, 25)),
    "25-29": list(range(25, 30)),
    "30-34": list(range(30, 35)),
    "35-39": list(range(35, 40)),
    "40-44": list(range(40, 45)),
    "45-49": list(range(45, 50)),
}


# ---------------------------------------------------------
# PROGRAMMI TÖÖSEADED
# ---------------------------------------------------------

# Väike paus API päringute vahel,
# et serverit mitte üle koormata
REQUEST_SLEEP = 0.08

# Kui True, siis väljastatakse prognoosi debug-info
DEBUG_FORECAST = False


# ---------------------------------------------------------
# STSENAARIUMITE JÄRJEKORD
# ---------------------------------------------------------

# Määrab, mis järjekorras stsenaariume kuvatakse
SCENARIO_ORDER = [
    "stat_amet_ilma_randeta",
    "stat_amet_randega",
    "praegune_tase_ilma_randeta",
    "praegune_tase_randega",
    "langev_ilma_randeta",
    "langev_randega",
]


# ---------------------------------------------------------
# GRAAFIKUTE STIILID
# ---------------------------------------------------------

# Iga stsenaariumi jaoks määratakse:
# - värv
# - joone tüüp
# - marker
#
# Kasutatakse matplotlib graafikute joonistamisel.
SCENARIO_STYLES = {
    "stat_amet_ilma_randeta": dict(color="tab:blue", linestyle="-", marker="o"),
    "stat_amet_randega": dict(color="tab:blue", linestyle="--", marker="s"),

    "praegune_tase_ilma_randeta": dict(color="tab:green", linestyle="-", marker="^"),
    "praegune_tase_randega": dict(color="tab:green", linestyle="--", marker="D"),

    "langev_ilma_randeta": dict(color="tab:red", linestyle="-", marker="v"),
    "langev_randega": dict(color="tab:red", linestyle="--", marker="P"),
}

# =========================================================
# ABI
# =========================================================
# Selles osas on abifunktsioonid, mida kasutatakse hiljem
# andmete puhastamiseks, API-st küsimiseks, tabelite ümberkujundamiseks
# ja prognooside jaoks vajalike väärtuste arvutamiseks.


def clean_colname(col: str) -> str:
    # Teisendab veeru nime tekstiks
    col = str(col)

    # Eemaldab võimalikud vigased märgid ja jutumärgid,
    # mis võivad tekkida CSV-faili lugemisel
    col = col.replace('ï»¿"', '').replace('ļ»æ"', '').replace('"', '')

    # Eemaldab UTF-8 BOM märgi, kui see on veeru nime alguses
    col = col.replace("\ufeff", "")

    # Eemaldab tühikud algusest ja lõpust
    return col.strip()


def normalize_label(text: str) -> str:
    # Teisendab sisendi tekstiks ja eemaldab liigsed tühikud
    t = str(text).strip()

    # Eemaldab algusest punktid, kui Statistikaameti nimetustes neid esineb
    while t.startswith("."):
        t = t[1:]

    # Tagastab puhastatud teksti väikeste tähtedega
    return t.strip().lower()


def get_metadata(url: str) -> dict:
    # Küsib Statistikaameti API-st tabeli metaandmed
    r = requests.get(url, timeout=60)

    # Kui päring ebaõnnestub, annab veateate
    r.raise_for_status()

    # Tagastab vastuse JSON kujul
    return r.json()


def px_post_csv(url: str, query: list[dict], debug_name: str = "") -> pd.DataFrame:
    # Koostab API päringu keha.
    # Vastuseks küsitakse CSV formaati.
    payload = {"query": query, "response": {"format": "csv"}}

    # Saadab POST päringu Statistikaameti API-sse
    r = requests.post(url, json=payload, timeout=120)

    # Kui API vastus ei ole korras, prinditakse detailne veainfo
    if not r.ok:
        print("\n--- API VIGA ---")
        print("Tabel:", debug_name or url)
        print("URL:", url)
        print("STATUS:", r.status_code)
        print("Päring:", payload)
        print("RESPONSE:", r.text[:1500])
        r.raise_for_status()

    # Dekodeerib vastuse tekstiks.
    # utf-8-sig eemaldab vajadusel BOM märgi.
    text = r.content.decode("utf-8-sig", errors="replace")

    # Loeb CSV vastuse pandas DataFrame'iks
    df = pd.read_csv(io.StringIO(text), sep=",")

    # Puhastab veergude nimed
    df.columns = [clean_colname(c) for c in df.columns]

    return df


def get_var(meta: dict, preferred_names: list[str]) -> str:
    # Otsib metaandmetest sobiva muutuja koodi.
    # Kõigepealt otsib täpset vastet koodi või nimetuse järgi.
    for pref in preferred_names:
        for v in meta["variables"]:
            if v["code"].lower() == pref.lower() or v["text"].lower() == pref.lower():
                return v["code"]

    # Kui täpset vastet ei leia, otsib osalist vastet
    for pref in preferred_names:
        for v in meta["variables"]:
            if pref.lower() in v["code"].lower() or pref.lower() in v["text"].lower():
                return v["code"]

    # Kui sobivat muutujat ei leita, antakse veateade
    raise ValueError(
        f"Ei leidnud muutujat. Otsiti: {preferred_names}. "
        f"Leitud: {[(v['code'], v['text']) for v in meta['variables']]}"
    )


def get_value_code(meta: dict, variable_code: str, label: str) -> str:
    # Otsib kindla muutuja väärtuse koodi nimetuse järgi.
    # Näiteks leiab "Rakvere vald" vastava API koodi.
    target = normalize_label(label)

    for var in meta["variables"]:
        if var["code"] == variable_code:
            # Paneb kokku väärtuse tekstid ja API koodid
            pairs = list(zip(var["valueTexts"], var["values"]))

            # Kõigepealt otsib täpset vastet
            for txt, val in pairs:
                if normalize_label(txt) == target:
                    return val

            # Kui täpset vastet pole, otsib osalist vastet
            for txt, val in pairs:
                if target in normalize_label(txt):
                    return val

            # Kui väärtust ei leita, annab veateate koos näidetega
            raise ValueError(
                f"'{label}' ei leitud muutujas {variable_code}. "
                f"Näiteid: {[p[0] for p in pairs[:40]]}"
            )

    raise ValueError(f"Muutujat {variable_code} ei leitud metadata sees.")


def get_single_age_pairs(meta: dict, age_var_code: str) -> list[tuple[int, str]]:
    # Leiab metaandmetest üksikvanused ja nende API koodid.
    # Tagastab paarid kujul: vanus, kood.
    for var in meta["variables"]:
        if var["code"] == age_var_code:
            pairs = []

            for code, txt in zip(var["values"], var["valueTexts"]):
                txt_norm = normalize_label(txt)

                # Alles jäetakse ainult need vanused,
                # mis on ühe konkreetse arvuna
                if txt_norm.isdigit():
                    age = int(txt_norm)
                    pairs.append((age, code))

            # Sorteerib vanused kasvavalt
            return sorted(pairs, key=lambda x: x[0])

    raise ValueError(f"Vanuse muutujat {age_var_code} ei leitud.")


def melt_wide_time_age(df: pd.DataFrame) -> pd.DataFrame:
    # Teisendab laia tabeli pikaks tabeliks.
    # Näiteks veerud "2020 1", "2020 2" jne muudetakse ridadeks.

    # ID veerud on need, mis ei alga kujul "aasta + muu tekst"
    id_cols = [c for c in df.columns if not re.search(r"\d{4}\s+.+", c)]

    # Väärtusveerud on kõik ülejäänud veerud
    value_cols = [c for c in df.columns if c not in id_cols]

    # Teisendab tabeli pikale kujule
    long_df = df.melt(
        id_vars=id_cols,
        value_vars=value_cols,
        var_name="time_key",
        value_name="value"
    )

    # Eraldab veeru nimest aasta ja alamvõtme
    extracted = long_df["time_key"].str.extract(r"(\d{4})\s+(.+)")
    long_df["year"] = pd.to_numeric(extracted[0], errors="coerce")
    long_df["subkey"] = extracted[1]

    # Teisendab väärtuse arvuks
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")

    # Eemaldab read, kus aasta või väärtus puudub
    long_df = long_df.dropna(subset=["year", "value"]).copy()

    # Teisendab aasta täisarvuks
    long_df["year"] = long_df["year"].astype(int)

    return long_df


def ensure_columns(df: pd.DataFrame, cols: list[int], fill_value: float = 0.0) -> pd.DataFrame:
    # Kontrollib, et DataFrame'is oleksid kõik vajalikud veerud olemas.
    # Kui mõni veerg puudub, lisatakse see vaikimisi väärtusega.
    out = df.copy()

    for c in cols:
        if c not in out.columns:
            out[c] = fill_value

    # Tagastab veerud sorteeritud järjekorras
    return out[sorted(out.columns)]


def pivot_year_age(df_long: pd.DataFrame, age_col: str = "age") -> pd.DataFrame:
    # Teeb pika tabeli ümber kujule:
    # read = aastad
    # veerud = vanused
    # väärtused = inimeste arv või muu arvuline näitaja
    return (
        df_long.pivot_table(index="year", columns=age_col, values="value", aggfunc="sum")
        .sort_index()
    )


def year_columns(df: pd.DataFrame) -> list[str]:
    # Leiab DataFrame'ist need veerud, mille nimi on ainult neljakohaline aasta
    return [c for c in df.columns if re.fullmatch(r"\d{4}", str(c))]


def linear_tfr_path(start_tfr: float, years: list[int], target_year: int = 2050, target_tfr: float = 1.63) -> dict:
    # Koostab sündimuse lineaarse muutumise tee.
    # Sündimuskordaja liigub algtasemelt sihttasemeni kindlaks aastaks.

    out = {}
    start_year = years[0]

    for y in years:
        if y >= target_year:
            # Kui sihtaasta on käes või möödas, kasutatakse sihttaset
            out[y] = target_tfr
        else:
            # Arvutab, kui kaugel ollakse alg- ja sihtaasta vahel
            frac = (y - start_year) / (target_year - start_year)

            # Interpoleerib TFR väärtuse
            out[y] = start_tfr + frac * (target_tfr - start_tfr)

    return out


def constant_tfr_path(level: float, years: list[int]) -> dict:
    # Koostab stsenaariumi, kus sündimuskordaja püsib igal aastal sama
    return {y: level for y in years}


def declining_tfr_path(start_tfr: float, years: list[int], end_year: int = 2035, end_tfr: float = 1.00) -> dict:
    # Koostab stsenaariumi, kus sündimuskordaja langeb lineaarselt
    # algtasemelt lõpptasemeni.

    out = {}
    start_year = years[0]

    for y in years:
        if y >= end_year:
            # Kui lõppaasta on käes või möödas, kasutatakse lõpptaset
            out[y] = end_tfr
        else:
            # Arvutab aasta asukoha alg- ja lõppaasta vahel
            frac = (y - start_year) / (end_year - start_year)

            # Arvutab vastava TFR väärtuse
            out[y] = start_tfr + frac * (end_tfr - start_tfr)

    return out


def safe_mean(values, default=0.0):
    # Arvutab keskmise ainult nendest väärtustest, mis ei ole puuduvad.
    vals = [v for v in values if pd.notna(v)]

    # Kui sobivaid väärtusi pole, tagastab vaikimisi väärtuse
    return float(np.mean(vals)) if vals else float(default)


def parse_agegroup_range(label: str):
    # Teisendab vanuserühma teksti arvuliseks vahemikuks.
    # Näiteks:
    # "20-24" -> (20, 24)
    # "85 ja vanem" -> (85, None)
    # "5" -> (5, 5)

    txt = normalize_label(label)

    # Otsib vahemikku kujul 20-24
    m = re.match(r"(\d+)\s*-\s*(\d+)", txt)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Kui tekst on üksik arv, tagastab sama vanuse alguse ja lõpuna
    if txt.isdigit():
        a = int(txt)
        return a, a

    # Töötleb tekste kujul "85 ja vanem"
    if "ja vanem" in txt:
        m2 = re.match(r"(\d+)", txt)
        if m2:
            return int(m2.group(1)), None

    # Kui vanuserühma ei õnnestu tõlgendada
    return None


def find_matching_column(columns, patterns):
    # Otsib veergude hulgast esimese veeru,
    # mille nimes sisalduvad kõik etteantud mustrid.
    for c in columns:
        cn = normalize_label(c)
        if all(p in cn for p in patterns):
            return c

    return None


def extract_annual_series_from_stat_df(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """
    Teisendab Statistikaameti vastuse kujule:
    year | <value_name>

    Funktsioon toetab mitut võimalikku tabelikuju:
    1) eraldi veerg "Aasta" ja selle kõrval väärtusveerud
    2) aastad on veergudena, näiteks 2018, 2019, 2020
    3) aastad on veergude alguses, näiteks "2018 Poisid ja tüdrukud"
    """

    # Teeb tabelist koopia, et algset tabelit mitte muuta
    tmp = df.copy()

    # Puhastab veergude nimed
    tmp.columns = [clean_colname(c) for c in tmp.columns]

    # -----------------------------------------------------
    # Variant A: tabelis on eraldi aasta veerg
    # -----------------------------------------------------

    year_col = None

    # Otsib veergu nimega "Aasta"
    for c in tmp.columns:
        if normalize_label(c) == "aasta":
            year_col = c
            break

    if year_col is not None:
        # Kõik veerud peale aasta veeru
        non_year_cols = [c for c in tmp.columns if c != year_col]

        # Leiab arvulised väärtusveerud
        numeric_candidates = []
        for c in non_year_cols:
            s = pd.to_numeric(tmp[c], errors="coerce")
            if s.notna().sum() > 0:
                numeric_candidates.append(c)

        if len(numeric_candidates) >= 1:
            # Võtab aasta veeru ja arvulised väärtusveerud
            out = tmp[[year_col] + numeric_candidates].copy()

            # Teisendab aasta ja väärtused arvudeks
            out[year_col] = pd.to_numeric(out[year_col], errors="coerce")
            for c in numeric_candidates:
                out[c] = pd.to_numeric(out[c], errors="coerce")

            # Eemaldab read, kus aasta puudub
            out = out.dropna(subset=[year_col]).copy()

            # Loob ühtse aasta veeru
            out["year"] = out[year_col].astype(int)

            # Liidab kõik arvulised väärtusveerud üheks väärtuseks
            out[value_name] = out[numeric_candidates].sum(axis=1)

            # Koondab tulemuse aasta kaupa
            return out[["year", value_name]].groupby("year", as_index=False)[value_name].sum()

    # -----------------------------------------------------
    # Variant B: aastad on veergude nimede alguses
    # -----------------------------------------------------

    year_like_cols = []

    # Leiab veerud, mis algavad neljakohalise aastaga
    for c in tmp.columns:
        if re.match(r"^\d{4}\b", str(c).strip()):
            year_like_cols.append(c)

    if len(year_like_cols) > 0:
        # Kõik ülejäänud veerud on ID veerud
        id_cols = [c for c in tmp.columns if c not in year_like_cols]

        # Teisendab laia tabeli pikaks tabeliks
        long_df = tmp.melt(
            id_vars=id_cols,
            value_vars=year_like_cols,
            var_name="year_raw",
            value_name=value_name
        )

        # Eraldab veeru nimest aasta
        long_df["year"] = long_df["year_raw"].astype(str).str.extract(r"^(\d{4})")[0]

        # Teisendab aasta ja väärtuse arvuliseks
        long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce")
        long_df[value_name] = pd.to_numeric(long_df[value_name], errors="coerce")

        # Eemaldab puuduvate väärtustega read
        long_df = long_df.dropna(subset=["year", value_name]).copy()

        # Teisendab aasta täisarvuks
        long_df["year"] = long_df["year"].astype(int)

        # Koondab väärtused aasta kaupa
        return long_df.groupby("year", as_index=False)[value_name].sum()

    # Kui ükski toetatud tabelikuju ei sobinud, antakse veateade
    raise ValueError(f"Ei suutnud tabelist aastaseeriat välja lugeda. Veerud: {tmp.columns.tolist()}")
# =========================================================
# 1) RV0240 - RAHVASTIK
# =========================================================
# Selles plokis loetakse Statistikaameti tabelist RV0240
# Rakvere valla rahvastikuandmed soo, vanuse ja aasta järgi.

print("1/12 Loen RV0240 metadata...")

# Loeb RV0240 tabeli metaandmed.
# Metaandmetest saab teada, millised muutujad ja väärtused tabelis olemas on.
meta_pop = get_metadata(TABLE_POP)

# Leiab metaandmetest vajalike muutujate koodid.
# API päringutes ei kasutata alati nähtavaid nimesid, vaid muutujakoode.
var_sex_pop = get_var(meta_pop, ["Sugu"])
var_place_pop = get_var(meta_pop, ["Elukoht"])
var_year_pop = get_var(meta_pop, ["Aasta"])
var_age_pop = get_var(meta_pop, ["Vanus"])

# Leiab meeste ja naiste API-koodid.
# Neid koode kasutatakse hiljem eraldi meeste ja naiste rahvastiku küsimiseks.
sex_m_code = get_value_code(meta_pop, var_sex_pop, "Mehed")
sex_f_code = get_value_code(meta_pop, var_sex_pop, "Naised")

# Leiab Rakvere valla API-koodi elukoha muutujas.
place_code_pop = get_value_code(meta_pop, var_place_pop, MUNICIPALITY_LABEL)

# Leiab kõik üksikvanused ja nende API-koodid.
# Tulemus on kujul: [(0, kood), (1, kood), (2, kood), ...]
single_age_pairs_pop = get_single_age_pairs(meta_pop, var_age_pop)

# Võtab eelmisest tulemusest ainult vanused eraldi listi.
single_ages_pop = [age for age, code in single_age_pairs_pop]

# Prindib kontrolliks, mitu üksikvanust leiti ning mis on vanusevahemik.
print("RV0240 üksikvanuseid leitud:", len(single_age_pairs_pop))
print("Min vanus:", min(single_ages_pop), "Max vanus:", max(single_ages_pop))


def fetch_population_for_sex(sex_code: str) -> pd.DataFrame:
    # Funktsioon loeb rahvastikuandmed ühe soo kohta.
    # Sisendiks antakse soo API-kood, näiteks meeste või naiste kood.
    # Tagastab tabeli, kus:
    # read = aastad
    # veerud = vanused
    # väärtused = inimeste arv

    # Siia kogutakse kõik API päringute tulemused
    parts = []

    # Vanuseid küsitakse väiksemate plokkidena.
    # See aitab vältida liiga suuri API päringuid.
    chunk_size = 10

    # Jagab kõik vanused 10 vanuse kaupa tükkideks
    age_chunks = [
        single_age_pairs_pop[i:i + chunk_size]
        for i in range(0, len(single_age_pairs_pop), chunk_size)
    ]

    # Käib läbi kõik ajaloolised aastad
    for y in POP_HISTORY_YEARS:

        # Käib iga aasta sees läbi kõik vanuseplokid
        for chunk in age_chunks:

            # Võtab vanuseplokist API-koodid
            age_codes_chunk = [code for age, code in chunk]

            # Võtab vanuseplokist vanused, et neid printida ja hiljem kontrollida
            age_values_chunk = [age for age, code in chunk]

            # Prindib jooksvalt, mida parajasti API-st küsitakse
            print(
                f"RV0240: sugu={sex_code}, aasta={y}, "
                f"vanused={age_values_chunk[0]}-{age_values_chunk[-1]}"
            )

            # Koostab Statistikaameti API päringu.
            # Filtreeritakse:
            # - sugu
            # - elukoht ehk Rakvere vald
            # - aasta
            # - vanuseplokk
            query = [
                {
                    "code": var_sex_pop,
                    "selection": {
                        "filter": "item",
                        "values": [sex_code]
                    }
                },
                {
                    "code": var_place_pop,
                    "selection": {
                        "filter": "item",
                        "values": [place_code_pop]
                    }
                },
                {
                    "code": var_year_pop,
                    "selection": {
                        "filter": "item",
                        "values": [str(y)]
                    }
                },
                {
                    "code": var_age_pop,
                    "selection": {
                        "filter": "item",
                        "values": age_codes_chunk
                    }
                },
            ]

            # Saadab päringu API-sse ja saab tulemuse DataFrame'ina
            raw = px_post_csv(
                TABLE_POP,
                query,
                debug_name=f"RV0240 year={y} ages={age_values_chunk[0]}-{age_values_chunk[-1]}"
            )

            # Lisab saadud tulemuse listi
            parts.append(raw)

            # Teeb väikese pausi, et API-d mitte liiga kiiresti päringutega koormata
            time.sleep(REQUEST_SLEEP)

    # Ühendab kõik väikeste päringute tulemused üheks suureks tabeliks
    raw_all = pd.concat(parts, ignore_index=True)

    # Teisendab Statistikaameti laia kujuga tabeli pikaks tabeliks.
    # Tekivad veerud näiteks: year, subkey, value
    long_df = melt_wide_time_age(raw_all)

    # subkey sisaldab selles tabelis vanust.
    # Teisendame selle arvuliseks vanuse veeruks.
    long_df["age"] = pd.to_numeric(long_df["subkey"], errors="coerce")

    # Eemaldab read, kus vanust ei õnnestunud arvuks teisendada
    long_df = long_df.dropna(subset=["age"]).copy()

    # Teisendab vanuse täisarvuks
    long_df["age"] = long_df["age"].astype(int)

    # Teeb pikast tabelist pivot-tabeli:
    # read = aastad
    # veerud = vanused
    # väärtused = inimeste arv
    pivot = pivot_year_age(long_df, age_col="age")

    # Kontrollib, et kõik üksikvanused oleksid veergudena olemas.
    # Kui mõni vanus puudub, lisatakse see väärtusega 0.
    pivot = ensure_columns(pivot, single_ages_pop, fill_value=0.0)

    return pivot


print("2/12 Loen RV0240 meeste andmed...")

# Loeb meeste rahvastikuandmed
pop_m = fetch_population_for_sex(sex_m_code)


print("3/12 Loen RV0240 naiste andmed...")

# Loeb naiste rahvastikuandmed
pop_f = fetch_population_for_sex(sex_f_code)


# Liidab meeste ja naiste rahvastiku kokku.
# Tulemus on kogu rahvastik vanuse ja aasta järgi.
pop_both = pop_m.add(pop_f, fill_value=0.0)


# Leiab kõige uuema aasta, mis rahvastikuandmetes olemas on.
# Seda kasutatakse prognoosi baas-aastana.
BASE_YEAR = int(pop_both.index.max())


# Leiab suurima vanuse, mis andmetes olemas on.
MAX_AGE = max(single_ages_pop)


# Loob kõikide vanuste järjestatud listi minimaalsest vanusest maksimaalseni.
AGES_ALL = list(range(min(single_ages_pop), MAX_AGE + 1))


# Prindib välja prognoosi baas-aasta.
print("Rahvastiku baas-aasta:", BASE_YEAR)


# =========================================================
# 2) RAHVASTIKUPÜRAMIID
# =========================================================
print("4/12 Joonistan rahvastikupüramiidi...")

def plot_population_pyramid(pop_m_df: pd.DataFrame, pop_f_df: pd.DataFrame, year: int, save_path: str):
    ages = sorted(set(pop_m_df.columns).intersection(set(pop_f_df.columns)))
    males = pop_m_df.loc[year, ages].astype(float)
    females = pop_f_df.loc[year, ages].astype(float)

    plt.figure(figsize=(11, 14))
    plt.barh(ages, -males.values, label="Mehed")
    plt.barh(ages, females.values, label="Naised")
    plt.axvline(0, linewidth=1)
    plt.yticks(np.arange(min(ages), max(ages) + 1, 5))
    plt.xlabel("Rahvaarv")
    plt.ylabel("Vanus")
    plt.title(f"Rakvere valla rahvastikupüramiid, {year}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=200)
    plt.show()

plot_population_pyramid(pop_m, pop_f, BASE_YEAR, "rakvere_rahvastikupuramiid.png")

# Rahvastikupüramiidi andmed Superseti jaoks
pyramid_rows = []

ages = sorted(set(pop_m.columns).intersection(set(pop_f.columns)))

for age in ages:
    pyramid_rows.append({
        "aasta": BASE_YEAR,
        "vanus": int(age),
        "sugu": "Mehed",
        "rahvaarv": float(pop_m.loc[BASE_YEAR, age]),
        "rahvaarv_puramiid": -float(pop_m.loc[BASE_YEAR, age])
    })

    pyramid_rows.append({
        "aasta": BASE_YEAR,
        "vanus": int(age),
        "sugu": "Naised",
        "rahvaarv": float(pop_f.loc[BASE_YEAR, age]),
        "rahvaarv_puramiid": float(pop_f.loc[BASE_YEAR, age])
    })

population_pyramid_df = pd.DataFrame(pyramid_rows)

population_pyramid_df.to_csv(
    OUTPUT_DIR / "rakvere_rahvastikupuramiid_andmed.csv",
    index=False,
    encoding="utf-8-sig"
)

# =========================================================
# 3) RV172 - SÜNDIMUSE VANUSKORDAJAD
# =========================================================
# Selles plokis loetakse Statistikaameti tabelist RV172
# sündimuse vanuskordajad vanuserühmade kaupa.
# Neid kasutatakse hiljem sündide prognoosimiseks.

print("5/12 Loen RV172 sündimuse vanuskordajad...")


# Loeb RV172 tabeli metaandmed
meta_asfr = get_metadata(TABLE_ASFR)

# Leiab API jaoks vajalike muutujate koodid:
# - aasta
# - näitaja ehk sündimuse vanuskordaja tüüp
var_year_asfr = get_var(meta_asfr, ["Aasta"])
var_indicator_asfr = get_var(meta_asfr, ["Näitaja"])


# Otsib metaandmetest üles vastavad muutuja objektid.
# Need sisaldavad võimalikke väärtusi ja nende koode.
indicator_obj = [v for v in meta_asfr["variables"] if v["code"] == var_indicator_asfr][0]
year_obj_asfr = [v for v in meta_asfr["variables"] if v["code"] == var_year_asfr][0]


# Siia salvestatakse vajalike vanuserühmade API-koodid.
# Alguses on väärtused None, hiljem asendatakse need õigete koodidega.
wanted_groups = {
    "15-19": None,
    "20-24": None,
    "25-29": None,
    "30-34": None,
    "35-39": None,
    "40-44": None,
    "45-49": None,
    "15-49_total": None,
}


# Käib läbi kõik RV172 tabelis olevad näitajad.
# Otsib nende hulgast vanuserühmade sündimuskordajad.
# Tingimus "1000" tähendab, et otsitakse kordajaid 1000 naise kohta.
for txt, code in zip(indicator_obj["valueTexts"], indicator_obj["values"]):
    t = normalize_label(txt)

    if "15-19" in t and "1000" in t:
        wanted_groups["15-19"] = code
    elif "20-24" in t and "1000" in t:
        wanted_groups["20-24"] = code
    elif "25-29" in t and "1000" in t:
        wanted_groups["25-29"] = code
    elif "30-34" in t and "1000" in t:
        wanted_groups["30-34"] = code
    elif "35-39" in t and "1000" in t:
        wanted_groups["35-39"] = code
    elif "40-44" in t and "1000" in t:
        wanted_groups["40-44"] = code
    elif "45-49" in t and "1000" in t:
        wanted_groups["45-49"] = code
    elif "15-49" in t and "1000" in t:
        wanted_groups["15-49_total"] = code


# Valib ainult need aastad, mida kasutatakse sündimuse ajaloolise taseme leidmiseks.
# Siin kasutatakse aastaid 2015–2024.
available_asfr_years = [
    y for y in year_obj_asfr["values"]
    if 2015 <= int(y) <= 2024
]


# Koostab API päringu:
# - valitud aastad
# - valitud sündimuse vanuserühmad
query_asfr = [
    {
        "code": var_year_asfr,
        "selection": {
            "filter": "item",
            "values": available_asfr_years
        }
    },
    {
        "code": var_indicator_asfr,
        "selection": {
            "filter": "item",
            "values": list(wanted_groups.values())
        }
    },
]


# Saadab päringu Statistikaameti API-sse ja saab tulemuse DataFrame'ina
asfr_raw = px_post_csv(TABLE_ASFR, query_asfr, debug_name="RV172")


# ---------------------------------------------------------
# Veergude ümbernimetamine
# ---------------------------------------------------------
# Statistikaameti tabeli veerunimed võivad olla pikad.
# Siin muudetakse need lihtsamateks nimedeks:
# näiteks "15-19 ... 1000 naise kohta" -> "15-19"

rename_map = {}

for col in asfr_raw.columns:
    c = normalize_label(col)

    if c == "aasta":
        rename_map[col] = "year"
    elif "15-19" in c and "1000" in c:
        rename_map[col] = "15-19"
    elif "20-24" in c and "1000" in c:
        rename_map[col] = "20-24"
    elif "25-29" in c and "1000" in c:
        rename_map[col] = "25-29"
    elif "30-34" in c and "1000" in c:
        rename_map[col] = "30-34"
    elif "35-39" in c and "1000" in c:
        rename_map[col] = "35-39"
    elif "40-44" in c and "1000" in c:
        rename_map[col] = "40-44"
    elif "45-49" in c and "1000" in c:
        rename_map[col] = "45-49"
    elif "15-49" in c and "1000" in c:
        rename_map[col] = "15-49_total"


# Rakendab uued veerunimed
asfr_df = asfr_raw.rename(columns=rename_map).copy()


# Need veerud peavad edasiseks arvutuseks olemas olema
required_cols = [
    "year",
    "15-19",
    "20-24",
    "25-29",
    "30-34",
    "35-39",
    "40-44",
    "45-49",
    "15-49_total"
]


# Teisendab aasta arvuks
asfr_df["year"] = pd.to_numeric(asfr_df["year"], errors="coerce")


# Teisendab sündimuskordajad arvudeks.
# Kuna näitajad on 1000 naise kohta, jagatakse need 1000-ga.
# Näiteks 45 sündi 1000 naise kohta muutub väärtuseks 0.045.
for c in required_cols[1:]:
    asfr_df[c] = pd.to_numeric(asfr_df[c], errors="coerce") / 1000.0


# Eemaldab read, kus aasta puudub
asfr_df = asfr_df.dropna(subset=["year"]).copy()

# Teisendab aasta täisarvuks
asfr_df["year"] = asfr_df["year"].astype(int)

# Sorteerib andmed aasta järgi
asfr_df = asfr_df.sort_values("year")


# Teeb tabeli kujule:
# indeks = aasta
# veerud = vanuserühmade sündimuskordajad
asfr_pivot = asfr_df.set_index("year")[required_cols[1:]].copy()


# Leiab viimase aasta, mille kohta sündimuse vanuskordajad olemas on
recent_asfr_year = int(asfr_pivot.index.max())


# Arvutab viimase aasta summaarse sündimuskordaja ehk TFR.
# Kuna vanuserühmad on 5 aasta laiused, korrutatakse vanuserühmade
# sündimuskordajate summa 5-ga.
tfr_recent = float(
    5 * (
        asfr_pivot.loc[recent_asfr_year, "15-19"] +
        asfr_pivot.loc[recent_asfr_year, "20-24"] +
        asfr_pivot.loc[recent_asfr_year, "25-29"] +
        asfr_pivot.loc[recent_asfr_year, "30-34"] +
        asfr_pivot.loc[recent_asfr_year, "35-39"] +
        asfr_pivot.loc[recent_asfr_year, "40-44"] +
        asfr_pivot.loc[recent_asfr_year, "45-49"]
    )
)


# Kuvab viimase teadaoleva TFR väärtuse
print("Viimane teadaolev TFR RV172 põhjal:", round(tfr_recent, 4))


# ---------------------------------------------------------
# Sündimuse stsenaariumid
# ---------------------------------------------------------
# Siin luuakse kolm erinevat sündimuse arenguteed,
# mida kasutatakse hiljem rahvastiku ja lasteaiakohtade prognoosis.

TFR_SCENARIOS = {
    # Stsenaarium 1:
    # sündimus liigub lineaarselt Statistikaameti pikaajalise sihttaseme poole
    "stat_amet": linear_tfr_path(
        start_tfr=tfr_recent,
        years=FORECAST_YEARS,
        target_year=2050,
        target_tfr=TFR_TARGET_2050
    ),

    # Stsenaarium 2:
    # sündimus jääb samale tasemele nagu viimasel teadaoleval aastal
    "praegune_tase": constant_tfr_path(
        level=tfr_recent,
        years=FORECAST_YEARS
    ),

    # Stsenaarium 3:
    # sündimus langeb prognoosiperioodi jooksul.
    # Lõpptase on kas 0.90 või viimase TFR-i tase miinus 0.15,
    # sõltuvalt sellest, kumb on suurem.
    "langev": declining_tfr_path(
        start_tfr=tfr_recent,
        years=FORECAST_YEARS,
        end_year=2035,
        end_tfr=max(0.90, tfr_recent - 0.15)
    )
}

# =========================================================
# 4) RV112U - SÜNNID
# =========================================================
# Selles plokis loetakse Statistikaameti tabelist RV112U
# Rakvere valla sündide arv aastate kaupa.

print("6/12 Loen RV112U sündide andmed...")


# Loeb RV112U tabeli metaandmed
meta_births = get_metadata(TABLE_BIRTHS)

# Leiab API päringuks vajalike muutujate koodid:
# - aasta
# - haldusüksus
# - sugu
var_year_births = get_var(meta_births, ["Aasta"])
var_place_births = get_var(
    meta_births,
    ["Haldusüksus", "Asustuspiirkonna", "Haldusüksus/ asustuspiirkonna liik"]
)
var_sex_births = get_var(meta_births, ["Sugu"])


# Leiab Rakvere valla koodi sündide tabelis
place_code_births = get_value_code(meta_births, var_place_births, MUNICIPALITY_LABEL)

# Leiab koodi, mis tähistab mõlemat sugu kokku:
# "Poisid ja tüdrukud"
sex_both_births = get_value_code(meta_births, var_sex_births, "Poisid ja tüdrukud")


# Leiab aasta muutuja objekti metaandmetest.
# Seda kasutatakse saadaolevate aastate nimekirja võtmiseks.
year_obj_births = [
    v for v in meta_births["variables"]
    if v["code"] == var_year_births
][0]


# Valib sündide andmetest aastad 2018–2024
available_birth_years = [
    y for y in year_obj_births["values"]
    if 2018 <= int(y) <= 2024
]


# Koostab API päringu:
# - valitud aastad
# - Rakvere vald
# - poisid ja tüdrukud kokku
query_births = [
    {
        "code": var_year_births,
        "selection": {
            "filter": "item",
            "values": available_birth_years
        }
    },
    {
        "code": var_place_births,
        "selection": {
            "filter": "item",
            "values": [place_code_births]
        }
    },
    {
        "code": var_sex_births,
        "selection": {
            "filter": "item",
            "values": [sex_both_births]
        }
    },
]


# Saadab päringu Statistikaameti API-sse
# ja saab sündide andmed DataFrame'ina
births_raw = px_post_csv(TABLE_BIRTHS, query_births, debug_name="RV112U")


# Teisendab API vastuse lihtsasse kujule:
# year | births
births_hist_df = extract_annual_series_from_stat_df(births_raw, "births")


# Muudab sündide ajaloolise tabeli sõnastikuks.
# Võti = aasta
# väärtus = sündide arv
# Seda on hiljem mugav prognoosis kasutada.
actual_births = births_hist_df.set_index("year")["births"].to_dict()


# Prindib kontrolliks Rakvere valla sündide tabeli
print("Rakvere valla sünnid:")
print(births_hist_df)

# =========================================================
# 4b) RV49U - SURMAD
# =========================================================
# Selles plokis loetakse Statistikaameti tabelist RV49U
# Rakvere valla surmade arv aastate kaupa.

print("7/12 Loen RV49U surmade andmed...")


# Loeb RV49U tabeli metaandmed
meta_deaths = get_metadata(TABLE_DEATHS)

# Leiab API päringuks vajalike muutujate koodid:
# - aasta
# - haldusüksus
# - sugu
var_year_deaths = get_var(meta_deaths, ["Aasta"])
var_place_deaths = get_var(
    meta_deaths,
    ["Haldusüksus", "Asustuspiirkonna", "Haldusüksus/ asustuspiirkonna liik"]
)
var_sex_deaths = get_var(meta_deaths, ["Sugu"])


# Leiab Rakvere valla koodi surmade tabelis
place_code_deaths = get_value_code(meta_deaths, var_place_deaths, MUNICIPALITY_LABEL)


# Leiab koodi, mis tähistab mehi ja naisi kokku.
# Mõnes tabelis võib selle väärtuse nimi olla "Mehed ja naised",
# mõnes aga "Kokku", seetõttu kasutatakse try-except lahendust.
try:
    sex_both_deaths = get_value_code(meta_deaths, var_sex_deaths, "Mehed ja naised")
except ValueError:
    sex_both_deaths = get_value_code(meta_deaths, var_sex_deaths, "Kokku")


# Leiab aasta muutuja objekti metaandmetest,
# et teada saada, millised aastad tabelis olemas on.
year_obj_deaths = [
    v for v in meta_deaths["variables"]
    if v["code"] == var_year_deaths
][0]


# Valib surmade andmetest aastad 2018–2024
available_death_years = [
    y for y in year_obj_deaths["values"]
    if 2018 <= int(y) <= 2024
]


# Koostab API päringu:
# - valitud aastad
# - Rakvere vald
# - mehed ja naised kokku
query_deaths = [
    {
        "code": var_year_deaths,
        "selection": {
            "filter": "item",
            "values": available_death_years
        }
    },
    {
        "code": var_place_deaths,
        "selection": {
            "filter": "item",
            "values": [place_code_deaths]
        }
    },
    {
        "code": var_sex_deaths,
        "selection": {
            "filter": "item",
            "values": [sex_both_deaths]
        }
    },
]


# Saadab päringu Statistikaameti API-sse
# ja saab surmade andmed DataFrame'ina
deaths_raw = px_post_csv(TABLE_DEATHS, query_deaths, debug_name="RV49U")


# Teisendab API vastuse lihtsasse kujule:
# year | deaths
deaths_hist_df = extract_annual_series_from_stat_df(deaths_raw, "deaths")


# Muudab surmade ajaloolise tabeli sõnastikuks.
# Võti = aasta
# väärtus = surmade arv
# Seda on hiljem mugav prognoosis kasutada.
actual_deaths = deaths_hist_df.set_index("year")["deaths"].to_dict()


# Prindib kontrolliks Rakvere valla surmade tabeli
print("Rakvere valla surmad:")
print(deaths_hist_df)

# =========================================================
# 5) KOHALIK SÜNDIMUSE KORRIGEERIMISTEGUR
# =========================================================
# Selles plokis arvutatakse Rakvere valla kohalik sündimuse korrigeerimistegur.
# Seda kasutatakse selleks, et riiklikud sündimuskordajad sobituksid paremini
# Rakvere valla tegelike sündide arvuga.

print("8/12 Arvutan Rakvere kohaliku sündimuse korrigeerimisteguri...")


# Siia kogutakse iga aasta kohta eraldi korrigeerimistegur.
# Hiljem võetakse neist keskmine.
local_fertility_factors = []


# Käib läbi aastad 2022, 2023 ja 2024,
# aga ainult siis, kui vajalikud andmed on olemas:
# - naiste rahvastik vanuse järgi
# - sündimuskordajad
# - tegelikud sünnid
for y in [
    yr for yr in [2022, 2023, 2024]
    if yr in pop_f.index and yr in asfr_pivot.index and yr in actual_births
]:

    # Võtab vastava aasta naiste rahvastiku vanuse kaupa
    women_y = pop_f.loc[y].astype(float)

    # Siia arvutatakse mudeli järgi oodatav sündide arv
    model_births = 0.0

    # Käib läbi sündimuse vanuserühmad,
    # näiteks 15-19, 20-24, 25-29 jne
    for grp, ages in ASFR_GROUPS.items():

        # Arvutab, mitu naist selles vanuserühmas Rakvere vallas oli
        women_in_group = float(women_y[ages].sum())

        # Võtab sama aasta sündimuskordaja selle vanuserühma jaoks
        rate = float(asfr_pivot.loc[y, grp])

        # Arvutab mudeli järgi sündide arvu:
        # naiste arv vanuserühmas × sündimuskordaja
        model_births += women_in_group * rate

    # Võtab tegeliku sündide arvu Rakvere vallas samal aastal
    actual_y = float(actual_births[y])

    # Kui mudel prognoosis rohkem kui 0 sündi,
    # arvutatakse tegeliku ja mudeli sündide suhe
    if model_births > 0:
        local_fertility_factors.append(actual_y / model_births)


# Arvutab 2022–2024 korrigeerimistegurite keskmise.
# Kui tegureid ei saanud arvutada, kasutatakse vaikimisi väärtust 1.0.
local_fertility_factor = safe_mean(local_fertility_factors, default=1.0)


# Prindib kohaliku korrigeerimisteguri.
# Kui tegur on üle 1, on Rakvere valla tegelik sündimus mudelist kõrgem.
# Kui tegur on alla 1, on tegelik sündimus mudelist madalam.
print("Rakvere kohaliku sündimuse korrigeerimistegur:", round(local_fertility_factor, 4))

# =========================================================
# 6) RVR02 - RÄNDE SALDO
# =========================================================
# Selles plokis loetakse Statistikaameti tabelist RVR02
# Rakvere valla rändesaldo andmed.
# Rändesaldo näitab, kas piirkonda kolis rohkem inimesi sisse või välja.

print("9/12 Loen RVR02 rände saldo andmed...")


# Loeb RVR02 tabeli metaandmed
meta_mig_muni = get_metadata(TABLE_MIG_MUNI)

# Leiab API päringuks vajalike muutujate koodid:
# - aasta
# - haldusüksus
var_year_mig_muni = get_var(meta_mig_muni, ["Aasta"])
var_place_mig_muni = get_var(meta_mig_muni, ["Haldusüksus", "Asustuspiirkonna"])


# Leiab Rakvere valla API-koodi rändetabelis
place_code_mig = get_value_code(meta_mig_muni, var_place_mig_muni, MUNICIPALITY_LABEL)


# Koostab API päringu:
# - aastad 2015–2024
# - Rakvere vald
query_mig_muni = [
    {
        "code": var_year_mig_muni,
        "selection": {
            "filter": "item",
            "values": [str(y) for y in range(2015, 2025)]
        }
    },
    {
        "code": var_place_mig_muni,
        "selection": {
            "filter": "item",
            "values": [place_code_mig]
        }
    },
]


# Saadab päringu Statistikaameti API-sse
# ja saab rändeandmed DataFrame'ina
mig_muni_raw = px_post_csv(TABLE_MIG_MUNI, query_mig_muni, debug_name="RVR02")


# ---------------------------------------------------------
# Vajalikud veerud tuvastatakse veerunimede järgi
# ---------------------------------------------------------

# Leiab aasta veeru
year_col = find_matching_column(mig_muni_raw.columns, ["aasta"])

# Leiab siserände saldo veeru
in_col = find_matching_column(mig_muni_raw.columns, ["rändesaldo", "siser"])

# Leiab välisrände saldo veeru
out_col = find_matching_column(mig_muni_raw.columns, ["rändesaldo", "välis"])


# Kui mõnda vajalikku veergu ei leita, lõpetatakse töö veateatega.
# See aitab märgata, kui API vastuse struktuur on muutunud.
if year_col is None or in_col is None or out_col is None:
    raise ValueError(
        f"RVR02 veergude tuvastamine ebaõnnestus. "
        f"Veerud: {mig_muni_raw.columns.tolist()}"
    )


# Võtab algsest tabelist ainult vajalikud veerud
mig_muni_df = mig_muni_raw[[year_col, in_col, out_col]].copy()

# Annab veergudele lihtsamad nimed
mig_muni_df.columns = [
    "year",
    "sisserande_saldo",
    "valisrande_saldo"
]


# Teisendab aasta ja rändesaldo väärtused arvudeks
mig_muni_df["year"] = pd.to_numeric(mig_muni_df["year"], errors="coerce")
mig_muni_df["sisserande_saldo"] = pd.to_numeric(
    mig_muni_df["sisserande_saldo"],
    errors="coerce"
)
mig_muni_df["valisrande_saldo"] = pd.to_numeric(
    mig_muni_df["valisrande_saldo"],
    errors="coerce"
)


# Eemaldab read, kus aasta puudub
mig_muni_df = mig_muni_df.dropna(subset=["year"]).copy()

# Teisendab aasta täisarvuks
mig_muni_df["year"] = mig_muni_df["year"].astype(int)


# Arvutab kogu netorände saldo:
# siserände saldo + välisrände saldo
mig_muni_df["kokku_netosaldo"] = (
    mig_muni_df["sisserande_saldo"] +
    mig_muni_df["valisrande_saldo"]
)


# Teeb rändesaldo veergudest aastapõhised seeriad.
# Neid kasutatakse hiljem prognoosis.
in_mig_hist = mig_muni_df.set_index("year")["sisserande_saldo"]
out_mig_hist = mig_muni_df.set_index("year")["valisrande_saldo"]
total_net_hist = mig_muni_df.set_index("year")["kokku_netosaldo"]


# Arvutab keskmise kogu netorände saldo.
# Kui aastad 2022–2024 on olemas, kasutatakse neid.
# Kui ei ole, kasutatakse kogu olemasoleva perioodi keskmist.
avg_net_migration_total = (
    float(total_net_hist.loc[MIG_HISTORY_YEARS].mean())
    if set(MIG_HISTORY_YEARS).issubset(set(total_net_hist.index))
    else float(total_net_hist.mean())
)


# Prindib keskmise netorände saldo.
# Positiivne väärtus tähendab, et inimesi tuli rohkem sisse kui lahkus.
# Negatiivne väärtus tähendab, et lahkujaid oli rohkem kui sisserändajaid.
print("Keskmine netorände saldo kokku:", round(avg_net_migration_total, 2))

# =========================================================
# 7) RVR03 - VANUSELINE RÄNDEPROFIIL
# =========================================================
print("10/12 Loen RVR03 vanuselise rände profiili...")

meta_mig_age = get_metadata(TABLE_MIG_AGE)
var_year_mig_age = get_var(meta_mig_age, ["Aasta"])
var_sex_mig_age = get_var(meta_mig_age, ["Sugu"])
var_agegroup_mig_age = get_var(meta_mig_age, ["Vanuserühm"])
var_type_mig_age = get_var(meta_mig_age, ["Rände liik"])
var_indicator_mig_age = get_var(meta_mig_age, ["Näitaja"])

sex_both_mig_age = get_value_code(meta_mig_age, var_sex_mig_age, "Mehed ja naised")

agegroup_obj = [v for v in meta_mig_age["variables"] if v["code"] == var_agegroup_mig_age][0]
agegroup_codes = agegroup_obj["values"]

indicator_obj_age = [v for v in meta_mig_age["variables"] if v["code"] == var_indicator_mig_age][0]
saldo_indicator_codes_age = []
for txt, code in zip(indicator_obj_age["valueTexts"], indicator_obj_age["values"]):
    if "saldo" in normalize_label(txt):
        saldo_indicator_codes_age.append(code)
if not saldo_indicator_codes_age:
    saldo_indicator_codes_age = indicator_obj_age["values"]

query_mig_age = [
    {"code": var_year_mig_age, "selection": {"filter": "item", "values": [str(y) for y in MIG_HISTORY_YEARS]}},
    {"code": var_sex_mig_age, "selection": {"filter": "item", "values": [sex_both_mig_age]}},
    {"code": var_agegroup_mig_age, "selection": {"filter": "item", "values": agegroup_codes}},
    {"code": var_type_mig_age, "selection": {"filter": "all", "values": ["*"]}},
    {"code": var_indicator_mig_age, "selection": {"filter": "item", "values": saldo_indicator_codes_age}},
]

mig_age_raw = px_post_csv(TABLE_MIG_AGE, query_mig_age, debug_name="RVR03")

mig_age_year_cols = year_columns(mig_age_raw)
mig_age_id_cols = [c for c in mig_age_raw.columns if c not in mig_age_year_cols]

mig_age_long = mig_age_raw.melt(
    id_vars=mig_age_id_cols,
    value_vars=mig_age_year_cols,
    var_name="year",
    value_name="value"
)
mig_age_long["year"] = pd.to_numeric(mig_age_long["year"], errors="coerce")
mig_age_long["value"] = pd.to_numeric(mig_age_long["value"], errors="coerce")
mig_age_long = mig_age_long.dropna(subset=["year", "value"]).copy()
mig_age_long["year"] = mig_age_long["year"].astype(int)

agegroup_col = None
for c in mig_age_id_cols:
    if "vanus" in c.lower():
        agegroup_col = c
        break
if agegroup_col is None:
    agegroup_col = mig_age_id_cols[0]

mig_age_profile = mig_age_long.groupby(agegroup_col)["value"].mean().reset_index()
mig_age_profile["parsed_range"] = mig_age_profile[agegroup_col].apply(parse_agegroup_range)
mig_age_profile = mig_age_profile.dropna(subset=["parsed_range"]).copy()

net_migration_age_shape = pd.Series(0.0, index=AGES_ALL, dtype=float)

for _, row in mig_age_profile.iterrows():
    val = float(row["value"])
    a, b = row["parsed_range"]
    if b is None:
        b = MAX_AGE
    b = min(b, MAX_AGE)

    ages_in_group = [x for x in range(a, b + 1) if x in net_migration_age_shape.index]
    if not ages_in_group:
        continue

    share_per_age = val / len(ages_in_group)
    for age in ages_in_group:
        net_migration_age_shape.loc[age] += share_per_age

shape_sum = float(net_migration_age_shape.sum())
if abs(shape_sum) < 1e-9:
    net_migration_age_shape[:] = 1.0 / len(net_migration_age_shape)
else:
    net_migration_age_shape = net_migration_age_shape / shape_sum

print("Kontroll: netorände vanuskuju summa =", round(float(net_migration_age_shape.sum()), 4))

# =========================================================
# 8) AJALOOLISED TABELID
# =========================================================
print("11/12 Koostan ajaloolised tabelid...")

birth_death_hist_df = pd.DataFrame({
    "aasta": sorted(set(actual_births.keys()).union(set(actual_deaths.keys())))
})
birth_death_hist_df["synnid"] = birth_death_hist_df["aasta"].map(actual_births).fillna(0.0)
birth_death_hist_df["surmad"] = birth_death_hist_df["aasta"].map(actual_deaths).fillna(0.0)
birth_death_hist_df["loomulik_iive"] = birth_death_hist_df["synnid"] - birth_death_hist_df["surmad"]

print("\nRakvere valla sündide ja surmade ajalooline tabel:")
print(birth_death_hist_df.to_string(index=False))

migration_plot_df = mig_muni_df.copy()

# =========================================================
# 9) SUREMUSMÄÄRAD
# =========================================================
print("12/12 Hinnan suremusmäärasid ja teen prognoosi...")

mortality_rate = pd.Series(0.0, index=AGES_ALL, dtype=float)

for age in AGES_ALL:
    estimates = []
    for y in [2022, 2023, 2024]:
        y_next = y + 1
        if y not in pop_both.index or y_next not in pop_both.index:
            continue
        if y not in total_net_hist.index:
            continue

        annual_mig_vector = net_migration_age_shape * float(total_net_hist.loc[y])

        if age < MAX_AGE:
            base = float(pop_both.loc[y, age])
            target_next = float(pop_both.loc[y_next, age + 1])
            mig_to_next_age = float(annual_mig_vector.loc[age + 1]) if (age + 1) in annual_mig_vector.index else 0.0

            if base > 0:
                survivors_est = target_next - mig_to_next_age
                mort = 1 - (survivors_est / base)
                mort = max(0.0, min(0.99, mort))
                estimates.append(mort)

    if len(estimates) > 0:
        mortality_rate.loc[age] = float(np.mean(estimates))

for age in AGES_ALL:
    if pd.isna(mortality_rate.loc[age]) or mortality_rate.loc[age] <= 0:
        if age <= 14:
            mortality_rate.loc[age] = 0.001
        elif age <= 49:
            mortality_rate.loc[age] = 0.003
        elif age <= 64:
            mortality_rate.loc[age] = 0.008
        elif age <= 74:
            mortality_rate.loc[age] = 0.025
        elif age <= 84:
            mortality_rate.loc[age] = 0.060
        elif age <= 94:
            mortality_rate.loc[age] = 0.150
        else:
            mortality_rate.loc[age] = 0.300

mortality_rate = mortality_rate.clip(lower=0.0005, upper=0.95)

# =========================================================
# 10) PROGNOOS 2026-2035
# =========================================================
# Selles plokis arvutatakse Rakvere valla rahvastiku,
# sündide, surmade, rände ja lasteaiakohtade prognoos aastateks 2026–2035.


# Võtab viimase teadaoleva aasta sündimuse vanuskordajad
# vanuserühmade kaupa.
recent_group_rates = asfr_pivot.loc[
    recent_asfr_year,
    list(ASFR_GROUPS.keys())
].astype(float).copy()


# Arvutab sündimuse vanusjaotuse.
# See näitab, kui suur osa sündimusest tuleb igast vanuserühmast.
# Hiljem muudetakse TFR taset, aga vanusjaotuse kuju jäetakse samaks.
group_shape = recent_group_rates / recent_group_rates.sum()


# Arvutab naiste osakaalu igas viljakas eas vanuses baas-aastal.
# Seda kasutatakse hiljem kogu rahvastikust naiste arvu ligikaudseks hindamiseks.
female_share_by_age = (
    pop_f.loc[BASE_YEAR, FERTILE_AGES] /
    pop_both.loc[BASE_YEAR, FERTILE_AGES].replace(0, np.nan)
).fillna(0.5)


# Siia kogutakse rahvastiku prognoosi tulemused
population_rows = []

# Siia kogutakse sündide prognoosi tulemused
birth_rows = []

# Siia kogutakse lasteaiakohtade vajaduse prognoosi tulemused
kinder_rows = []


# Arvutab keskmise aastase netorände.
# Kui MIG_HISTORY_YEARS aastad on olemas, kasutatakse neid.
# Vastasel juhul kasutatakse kogu olemasoleva rändeajaloo keskmist.
avg_annual_net_migration = (
    float(total_net_hist.loc[MIG_HISTORY_YEARS].mean())
    if set(MIG_HISTORY_YEARS).issubset(set(total_net_hist.index))
    else float(total_net_hist.mean())
)


# Käib läbi kõik sündimuse stsenaariumid:
# - stat_amet
# - praegune_tase
# - langev
for fertility_scenario, tfr_path in TFR_SCENARIOS.items():

    # Iga sündimuse stsenaariumi kohta arvutatakse kaks varianti:
    # - ilma rändeta
    # - rändega
    for migration_scenario in ["ilma_randeta", "randega"]:

        # Võtab baas-aasta rahvastiku vanuse kaupa.
        # See on prognoosi algseis.
        pop_prev = pop_both.loc[BASE_YEAR, AGES_ALL].astype(float).copy()


        # Käib läbi kõik prognoosiaastad 2026–2035
        for year in FORECAST_YEARS:

            # Kui stsenaarium sisaldab rännet,
            # jaotatakse keskmine netoränne vanuste vahel varasema vanusjaotuse järgi.
            if migration_scenario == "randega":
                annual_mig_vector = net_migration_age_shape * avg_annual_net_migration

            # Kui stsenaarium on ilma rändeta,
            # on rändemõju igas vanuses 0.
            else:
                annual_mig_vector = pd.Series(0.0, index=AGES_ALL, dtype=float)


            # Arvutab prognoositavad surmad vanuse kaupa:
            # rahvastik × suremuskordaja
            deaths_by_age = pop_prev * mortality_rate

            # Summeerib kõik surmad kokku
            total_deaths = float(deaths_by_age.sum())


            # Arvutab ellujäänud rahvastiku:
            # eelmise aasta rahvastik - surmad
            survivors = pop_prev - deaths_by_age

            # Negatiivseid väärtusi ei lubata
            survivors = survivors.clip(lower=0.0)


            # Loob järgmise aasta rahvastiku vektori vanuse kaupa
            next_pop = pd.Series(0.0, index=AGES_ALL, dtype=float)


            # Vanandab rahvastiku ühe aasta võrra.
            # Näiteks eelmise aasta 0-aastased liiguvad 1-aastasteks,
            # 1-aastased 2-aastasteks jne.
            for age in range(1, MAX_AGE):
                next_pop.loc[age] = float(survivors.loc[age - 1])


            # Kõige vanemas vanuserühmas liidetakse kokku:
            # - eelmisel aastal ühe aasta nooremad ellujäänud
            # - eelmisel aastal juba maksimaalses vanuses olnud ellujäänud
            next_pop.loc[MAX_AGE] = (
                float(survivors.loc[MAX_AGE - 1]) +
                float(survivors.loc[MAX_AGE])
            )


            # Lisab rahvastikule rändemõju vanuse kaupa
            next_pop = next_pop.add(annual_mig_vector, fill_value=0.0)

            # Jällegi välditakse negatiivseid rahvastikuarve
            next_pop = next_pop.clip(lower=0.0)


            # Hindab viljakas eas naiste arvu vanuse kaupa.
            # Kuna prognoosis hoitakse rahvastikku kokku, kasutatakse baas-aasta
            # naiste osakaalu vastavas vanuses.
            women_current = (
                next_pop[FERTILE_AGES] * female_share_by_age
            ).astype(float)


            # Võtab vastava aasta TFR väärtuse valitud sündimuse stsenaariumist
            tfr_y = tfr_path[year]


            # Jaotab TFR-i vanuserühmade vahel viimase teadaoleva vanusjaotuse järgi.
            # Jagamine 5-ga teisendab TFR-i tagasi vanuserühma aastaseks kordajaks,
            # sest vanuserühmad on 5 aasta laiused.
            group_rates_future = group_shape * (tfr_y / 5.0)


            # Arvutab sündide arvu riikliku vanusmustri põhjal
            births_national_pattern = 0.0

            for grp, ages in ASFR_GROUPS.items():
                # Naiste arv selles vanuserühmas
                women_in_group = float(women_current[ages].sum())

                # Sünnid selles vanuserühmas:
                # naiste arv × vanuserühma sündimuskordaja
                births_national_pattern += (
                    women_in_group * float(group_rates_future[grp])
                )


            # Kohandab sündide arvu Rakvere valla kohaliku sündimustasemega
            births_local = births_national_pattern * local_fertility_factor


            # Lisab sündinud järgmise aasta 0-aastasteks.
            # Kui rändemudel sisaldab ka 0-aastaste rännet,
            # lisatakse see samuti juurde.
            next_pop.loc[0] = max(
                0.0,
                births_local + float(annual_mig_vector.loc[0])
            )


            # Arvutab eelmise aasta kogurahvastiku
            total_population_prev = float(pop_prev.sum())

            # Arvutab järgmise aasta kogurahvastiku
            total_population = float(next_pop.sum())

            # Arvutab kogu rändesaldo antud aastal
            migration_total = float(annual_mig_vector.sum())

            # Arvutab loomuliku iibe:
            # sünnid - surmad
            natural_increase = births_local - total_deaths


            # Koostab stsenaariumi nime,
            # näiteks "stat_amet_randega"
            scenario_name = f"{fertility_scenario}_{migration_scenario}"


            # Salvestab rahvastiku prognoosi ühe rea
            population_rows.append({
                "stsenaarium_sundimus": fertility_scenario,
                "stsenaarium_ranne": migration_scenario,
                "stsenaarium": scenario_name,
                "aasta": year,
                "rahvaarv_eelmine_aasta": round(total_population_prev, 2),
                "rahvaarv_kokku": round(total_population, 2),
                "naised_15_49": round(float(women_current.sum()), 2),
                "prognoositud_synnid": round(births_local, 2),
                "prognoositud_surmad": round(total_deaths, 2),
                "loomulik_iive": round(natural_increase, 2),
                "randesaldo": round(migration_total, 2),
                "tfr": round(tfr_y, 4),
            })


            # Salvestab sündide ja iibe prognoosi ühe rea
            birth_rows.append({
                "stsenaarium_sundimus": fertility_scenario,
                "stsenaarium_ranne": migration_scenario,
                "stsenaarium": scenario_name,
                "aasta": year,
                "eesti_tfr_eeldus": round(tfr_y, 4),
                "rakvere_kohalik_korrigeerimistegur": round(local_fertility_factor, 4),
                "prognoositud_synnid": round(births_local, 2),
                "prognoositud_surmad": round(total_deaths, 2),
                "loomulik_iive": round(natural_increase, 2),
                "randesaldo": round(migration_total, 2),
                "naised_15_49": round(float(women_current.sum()), 2),
            })


            # Lasteaiakohtade vajadust arvutatakse ainult KINDER_YEARS aastate kohta.
            # Praegu tähendab see aastaid 2026–2030.
            if year in KINDER_YEARS:

                # Arvutab kogu lasteaiakohtade vajaduse vanustes 1–6.
                # Iga vanuse laste arv korrutatakse vastava osalusmääraga.
                total_need = sum(
                    next_pop[a] * PARTICIPATION_BY_AGE[a]
                    for a in ALL_KINDER_AGES
                    if a in next_pop.index
                )

                # Arvutab sõimekohtade ligikaudse vajaduse vanustes 1–2.
                small_need = sum(
                    next_pop[a] * PARTICIPATION_BY_AGE[a]
                    for a in SMALL_CHILD_AGES
                    if a in next_pop.index
                )


                # Erinevus olemasolevate lasteaiakohtadega.
                # Positiivne väärtus = kohti jääb puudu.
                # Negatiivne väärtus = kohti on üle.
                diff_total = total_need - TOTAL_KINDER_PLACES

                # Erinevus olemasolevate sõimekohtadega
                diff_small = small_need - PLACES_15_TO_3


                # Salvestab lasteaiakohtade prognoosi ühe rea
                kinder_rows.append({
                    "stsenaarium_sundimus": fertility_scenario,
                    "stsenaarium_ranne": migration_scenario,
                    "stsenaarium": scenario_name,
                    "aasta": year,
                    "prognoositud_synnid": round(births_local, 2),
                    "prognoositud_surmad": round(total_deaths, 2),
                    "loomulik_iive": round(natural_increase, 2),
                    "randesaldo": round(migration_total, 2),
                    "tfr": round(tfr_y, 4),
                    "rahvaarv_kokku": round(total_population, 2),
                    "naised_15_49": round(float(women_current.sum()), 2),

                    # Laste arv vanuste kaupa
                    "vanus_1": round(float(next_pop.get(1, 0)), 2),
                    "vanus_2": round(float(next_pop.get(2, 0)), 2),
                    "vanus_3": round(float(next_pop.get(3, 0)), 2),
                    "vanus_4": round(float(next_pop.get(4, 0)), 2),
                    "vanus_5": round(float(next_pop.get(5, 0)), 2),
                    "vanus_6": round(float(next_pop.get(6, 0)), 2),

                    # Kõik 1–6-aastased kokku
                    "lasteaiaealised_1_6": round(
                        sum(float(next_pop.get(a, 0)) for a in ALL_KINDER_AGES),
                        2
                    ),

                    # Vajalikud ja olemasolevad lasteaiakohad kokku
                    "vajalikud_kohad_kokku": round(total_need, 2),
                    "olemasolevad_kohad_kokku": TOTAL_KINDER_PLACES,
                    "puudu_voi_ule_kokku": round(diff_total, 2),
                    "uusi_kohti_vaja_kokku": max(0, math.ceil(diff_total)),

                    # Vajalikud ja olemasolevad sõimekohad
                    "vajalikud_kohad_1_5_3_ligikaudne": round(small_need, 2),
                    "olemasolevad_kohad_1_5_3": PLACES_15_TO_3,
                    "puudu_voi_ule_1_5_3": round(diff_small, 2),
                    "uusi_kohti_vaja_1_5_3": max(0, math.ceil(diff_small)),
                })


            # Kui DEBUG_FORECAST on True,
            # prinditakse vaheinfo kuni aastani 2030.
            # See on kasulik kontrolliks ja vigade otsimiseks.
            if DEBUG_FORECAST and year <= 2030:
                print(
                    f"{scenario_name} | {year} | "
                    f"P={round(total_population,1)} | "
                    f"B={round(births_local,1)} | "
                    f"D={round(total_deaths,1)} | "
                    f"M={round(migration_total,1)}"
                )


            # Uuendab rahvastiku järgmise tsükli jaoks.
            # Järgmise aasta arvutus algab sellest prognoositud rahvastikust.
            pop_prev = next_pop.copy()


# Teisendab kogutud read DataFrame'ideks.
# Neid kasutatakse hiljem tabelite eksportimiseks ja graafikute tegemiseks.
population_df = pd.DataFrame(population_rows)
birth_forecast_df = pd.DataFrame(birth_rows)
kinder_df = pd.DataFrame(kinder_rows)

# =========================================================
# 11) KOKKUVÕTVAD TABELID
# =========================================================
summary_table = (
    kinder_df.groupby(["stsenaarium_sundimus", "stsenaarium_ranne"], as_index=False)
    .agg(
        keskmine_rahvaarv_2026_2030=("rahvaarv_kokku", "mean"),
        rahvaarv_2030=("rahvaarv_kokku", "last"),
        keskmine_naised_15_49=("naised_15_49", "mean"),
        naised_15_49_2030=("naised_15_49", "last"),
        keskmine_synnid_2026_2030=("prognoositud_synnid", "mean"),
        keskmine_surmad_2026_2030=("prognoositud_surmad", "mean"),
        keskmine_loomulik_iive_2026_2030=("loomulik_iive", "mean"),
        keskmine_randesaldo_2026_2030=("randesaldo", "mean"),
        maks_synnid_2026_2030=("prognoositud_synnid", "max"),
        keskmine_vajalikud_kohad=("vajalikud_kohad_kokku", "mean"),
        maks_vajalikud_kohad=("vajalikud_kohad_kokku", "max"),
        maks_uusi_kohti_vaja=("uusi_kohti_vaja_kokku", "max"),
        keskmine_vajalikud_kohad_1_5_3=("vajalikud_kohad_1_5_3_ligikaudne", "mean"),
        maks_vajalikud_kohad_1_5_3=("vajalikud_kohad_1_5_3_ligikaudne", "max"),
        maks_uusi_kohti_vaja_1_5_3=("uusi_kohti_vaja_1_5_3", "max"),
    )
)

summary_table["piisab_204_kohast"] = np.where(summary_table["maks_vajalikud_kohad"] <= TOTAL_KINDER_PLACES, "jah", "ei")
summary_table["piisab_84_kohast_1_5_3"] = np.where(summary_table["maks_vajalikud_kohad_1_5_3"] <= PLACES_15_TO_3, "jah", "ei")

for c in [
    "keskmine_rahvaarv_2026_2030", "rahvaarv_2030",
    "keskmine_naised_15_49", "naised_15_49_2030",
    "keskmine_synnid_2026_2030", "keskmine_surmad_2026_2030",
    "keskmine_loomulik_iive_2026_2030", "keskmine_randesaldo_2026_2030",
    "maks_synnid_2026_2030",
    "keskmine_vajalikud_kohad", "maks_vajalikud_kohad",
    "keskmine_vajalikud_kohad_1_5_3", "maks_vajalikud_kohad_1_5_3"
]:
    summary_table[c] = summary_table[c].round(2)

yearly_compare_table = kinder_df.pivot_table(
    index="aasta",
    columns="stsenaarium",
    values="vajalikud_kohad_kokku",
    aggfunc="sum"
).round(2)

population_compare_table = population_df.pivot_table(
    index="aasta",
    columns="stsenaarium",
    values="rahvaarv_kokku",
    aggfunc="sum"
).round(2)

# =========================================================
# 12) FAILID JA GRAAFIKUD
# =========================================================
population_df.to_csv(OUTPUT_DIR / "rakvere_rahvastiku_prognoos_2026_2035.csv", index=False, encoding="utf-8-sig")
birth_forecast_df.to_csv(OUTPUT_DIR / "rakvere_synnid_2026_2035.csv", index=False, encoding="utf-8-sig")
kinder_df.to_csv(OUTPUT_DIR / "rakvere_lasteaiavajadus_2026_2030.csv", index=False, encoding="utf-8-sig")
summary_table.to_csv(OUTPUT_DIR / "rakvere_kokkuvottev_tabel.csv", index=False, encoding="utf-8-sig")
yearly_compare_table.to_csv(OUTPUT_DIR / "rakvere_aastate_vordlus_tabel.csv", encoding="utf-8-sig")
population_compare_table.to_csv(OUTPUT_DIR / "rakvere_rahvaarvu_vordlus_tabel.csv", encoding="utf-8-sig")
migration_plot_df.to_csv(OUTPUT_DIR / "rakvere_rande_saldo_2015_2024.csv", index=False, encoding="utf-8-sig")
birth_death_hist_df.to_csv(OUTPUT_DIR / "rakvere_synnid_surmad_2018_2024.csv", index=False, encoding="utf-8-sig")

print("\nKontroll: mitu rida igas stsenaariumis on?")
print("\nBirth forecast:")
print(birth_forecast_df.groupby("stsenaarium").size())
print("\nKinder:")
print(kinder_df.groupby("stsenaarium").size())
print("\nPopulation:")
print(population_df.groupby("stsenaarium").size())

print("\nKokkuvõttev tabel:")
print(summary_table.to_string(index=False))

# Ajalooline rändegraafik
plt.figure(figsize=(11, 6))
x = np.arange(len(migration_plot_df))
width = 0.35

plt.bar(x - width/2, migration_plot_df["sisserande_saldo"], width=width, label="Siserände saldo")
plt.bar(x + width/2, migration_plot_df["valisrande_saldo"], width=width, label="Välisrände saldo")
plt.plot(x, migration_plot_df["kokku_netosaldo"], marker="o", linewidth=2, label="Kogu netosaldo")

plt.axhline(0, linewidth=1)
plt.xticks(x, migration_plot_df["year"])
plt.title("Rakvere valla rändesaldo rände liigi järgi 2015–2024")
plt.xlabel("Aasta")
plt.ylabel("Saldo")
plt.grid(True, axis="y", alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rakvere_rande_saldo_2015_2024.png", dpi=200)
plt.show()

# Ajaloolised sünnid ja surmad
plt.figure(figsize=(11, 6))
plt.plot(birth_death_hist_df["aasta"], birth_death_hist_df["synnid"], marker="o", linewidth=2.2, label="Sünnid")
plt.plot(birth_death_hist_df["aasta"], birth_death_hist_df["surmad"], marker="o", linewidth=2.2, label="Surmad")
plt.plot(birth_death_hist_df["aasta"], birth_death_hist_df["loomulik_iive"], marker="o", linestyle="--", linewidth=2.0, label="Loomulik iive")
plt.axhline(0, linewidth=1)
plt.title("Rakvere valla sünnid ja surmad 2018–2024")
plt.xlabel("Aasta")
plt.ylabel("Arv")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rakvere_synnid_surmad_2018_2024.png", dpi=200)
plt.show()

# Prognoositud sünnid
plt.figure(figsize=(12, 7))
for scen in SCENARIO_ORDER:
    s = birth_forecast_df[birth_forecast_df["stsenaarium"] == scen].sort_values("aasta")
    if len(s) == 0:
        continue
    style = SCENARIO_STYLES.get(scen, {})
    plt.plot(
        s["aasta"],
        s["prognoositud_synnid"],
        label=scen,
        linewidth=2.2,
        markersize=7,
        zorder=3,
        **style
    )

plt.title("Rakvere valla prognoositud sünnid 2026–2035")
plt.xlabel("Aasta")
plt.ylabel("Sünnide arv")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rakvere_synnid_2026_2035.png", dpi=200)
plt.show()

# Prognoositud sünnid ja surmad kahes paneelis
fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)

for scen in SCENARIO_ORDER:
    s = birth_forecast_df[birth_forecast_df["stsenaarium"] == scen].sort_values("aasta")
    if len(s) == 0:
        continue
    style = SCENARIO_STYLES.get(scen, {})
    axes[0].plot(
        s["aasta"],
        s["prognoositud_synnid"],
        label=scen,
        linewidth=2.2,
        markersize=6,
        zorder=3,
        **style
    )

axes[0].set_title("Rakvere valla prognoositud sünnid 2026–2035")
axes[0].set_ylabel("Sünnide arv")
axes[0].grid(True, alpha=0.3)
axes[0].legend()

for scen in SCENARIO_ORDER:
    s = birth_forecast_df[birth_forecast_df["stsenaarium"] == scen].sort_values("aasta")
    if len(s) == 0:
        continue
    style = SCENARIO_STYLES.get(scen, {})
    axes[1].plot(
        s["aasta"],
        s["prognoositud_surmad"],
        label=scen,
        linewidth=2.2,
        markersize=6,
        zorder=3,
        **style
    )

axes[1].set_title("Rakvere valla prognoositud surmad 2026–2035")
axes[1].set_xlabel("Aasta")
axes[1].set_ylabel("Surmade arv")
axes[1].grid(True, alpha=0.3)
axes[1].legend()

plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rakvere_synnid_surmad_prognoos_2026_2035.png", dpi=200)
plt.show()

# Lasteaiakohad
plt.figure(figsize=(12, 7))
for scen in SCENARIO_ORDER:
    s = kinder_df[kinder_df["stsenaarium"] == scen].sort_values("aasta")
    if len(s) == 0:
        continue
    style = SCENARIO_STYLES.get(scen, {})
    plt.plot(
        s["aasta"],
        s["vajalikud_kohad_kokku"],
        label=scen,
        linewidth=2.2,
        markersize=7,
        zorder=3,
        **style
    )

plt.axhline(TOTAL_KINDER_PLACES, linestyle=":", linewidth=2.0, color="black", label="Olemasolevad kohad kokku")
plt.title("Rakvere valla lasteaiakohtade vajadus 2026–2030")
plt.xlabel("Aasta")
plt.ylabel("Kohtade arv")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rakvere_lasteaiakohad_2026_2030.png", dpi=200)
plt.show()

# Rahvaarvu prognoos
plt.figure(figsize=(12, 7))
for scen in SCENARIO_ORDER:
    s = population_df[population_df["stsenaarium"] == scen].sort_values("aasta")
    if len(s) == 0:
        continue
    style = SCENARIO_STYLES.get(scen, {})
    plt.plot(
        s["aasta"],
        s["rahvaarv_kokku"],
        label=scen,
        linewidth=2.2,
        markersize=7,
        zorder=3,
        **style
    )

plt.title("Rakvere valla rahvaarvu prognoos 2026–2035")
plt.xlabel("Aasta")
plt.ylabel("Rahvaarv")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "rakvere_rahvaarvu_prognoos_2026_2035.png", dpi=200)
plt.show()

print("\nFailid salvestatud:")
print("- rakvere_rahvastikupuramiid.png")
print("- rakvere_rande_saldo_2015_2024.png")
print("- rakvere_rande_saldo_2015_2024.csv")
print("- rakvere_synnid_surmad_2018_2024.csv")
print("- rakvere_synnid_surmad_2018_2024.png")
print("- rakvere_rahvastiku_prognoos_2026_2035.csv")
print("- rakvere_rahvaarvu_prognoos_2026_2035.png")
print("- rakvere_synnid_2026_2035.csv")
print("- rakvere_synnid_2026_2035.png")
print("- rakvere_synnid_surmad_prognoos_2026_2035.png")
print("- rakvere_lasteaiavajadus_2026_2030.csv")
print("- rakvere_lasteaiakohad_2026_2030.png")
print("- rakvere_kokkuvottev_tabel.csv")
print("- rakvere_aastate_vordlus_tabel.csv")
print("- rakvere_rahvaarvu_vordlus_tabel.csv")
print("- rakvere_rahvastikupuramiid_andmed.csv")