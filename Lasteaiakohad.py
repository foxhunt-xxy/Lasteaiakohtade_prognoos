import io
import re
import math
import time
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =========================================================
# SEADED
# =========================================================
BASE_URL = "https://andmed.stat.ee/api/v1/et/stat"

TABLE_POP = f"{BASE_URL}/RV0240"         # Rahvastik soo, vanuse ja elukoha järgi
TABLE_BIRTHS = f"{BASE_URL}/RV112U"      # Elussündinud soo ja haldusüksuse järgi
TABLE_DEATHS = f"{BASE_URL}/RV49U"       # Surnud soo ja haldusüksuse järgi
TABLE_ASFR = f"{BASE_URL}/RV172"         # Sündimuse vanuskordajad
TABLE_MIG_MUNI = f"{BASE_URL}/RVR02"     # Rände saldo haldusüksuse järgi
TABLE_MIG_AGE = f"{BASE_URL}/RVR03"      # Rände saldo vanuserühma järgi

MUNICIPALITY_LABEL = "Rakvere vald"

POP_HISTORY_YEARS = list(range(2015, 2026))
MIG_HISTORY_YEARS = [2022, 2023, 2024]
FORECAST_YEARS = list(range(2026, 2036))
KINDER_YEARS = list(range(2026, 2031))

TFR_TARGET_2050 = 1.63

TOTAL_KINDER_PLACES = 204
PLACES_15_TO_3 = 84

PARTICIPATION_BY_AGE = {
    1: 0.20,
    2: 0.75,
    3: 0.95,
    4: 0.97,
    5: 0.97,
    6: 0.97,
}

ALL_KINDER_AGES = [1, 2, 3, 4, 5, 6]
SMALL_CHILD_AGES = [1, 2]
FERTILE_AGES = list(range(15, 50))

ASFR_GROUPS = {
    "15-19": list(range(15, 20)),
    "20-24": list(range(20, 25)),
    "25-29": list(range(25, 30)),
    "30-34": list(range(30, 35)),
    "35-39": list(range(35, 40)),
    "40-44": list(range(40, 45)),
    "45-49": list(range(45, 50)),
}

REQUEST_SLEEP = 0.08
DEBUG_FORECAST = False

SCENARIO_ORDER = [
    "stat_amet_ilma_randeta",
    "stat_amet_randega",
    "praegune_tase_ilma_randeta",
    "praegune_tase_randega",
    "langev_ilma_randeta",
    "langev_randega",
]

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
def clean_colname(col: str) -> str:
    col = str(col)
    col = col.replace('ï»¿"', '').replace('ļ»æ"', '').replace('"', '')
    col = col.replace("\ufeff", "")
    return col.strip()

def normalize_label(text: str) -> str:
    t = str(text).strip()
    while t.startswith("."):
        t = t[1:]
    return t.strip().lower()

def get_metadata(url: str) -> dict:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()

def px_post_csv(url: str, query: list[dict], debug_name: str = "") -> pd.DataFrame:
    payload = {"query": query, "response": {"format": "csv"}}
    r = requests.post(url, json=payload, timeout=120)

    if not r.ok:
        print("\n--- API VIGA ---")
        print("Tabel:", debug_name or url)
        print("URL:", url)
        print("STATUS:", r.status_code)
        print("Päring:", payload)
        print("RESPONSE:", r.text[:1500])
        r.raise_for_status()

    text = r.content.decode("utf-8-sig", errors="replace")
    df = pd.read_csv(io.StringIO(text), sep=",")
    df.columns = [clean_colname(c) for c in df.columns]
    return df

def get_var(meta: dict, preferred_names: list[str]) -> str:
    for pref in preferred_names:
        for v in meta["variables"]:
            if v["code"].lower() == pref.lower() or v["text"].lower() == pref.lower():
                return v["code"]

    for pref in preferred_names:
        for v in meta["variables"]:
            if pref.lower() in v["code"].lower() or pref.lower() in v["text"].lower():
                return v["code"]

    raise ValueError(
        f"Ei leidnud muutujat. Otsiti: {preferred_names}. "
        f"Leitud: {[(v['code'], v['text']) for v in meta['variables']]}"
    )

def get_value_code(meta: dict, variable_code: str, label: str) -> str:
    target = normalize_label(label)
    for var in meta["variables"]:
        if var["code"] == variable_code:
            pairs = list(zip(var["valueTexts"], var["values"]))

            for txt, val in pairs:
                if normalize_label(txt) == target:
                    return val

            for txt, val in pairs:
                if target in normalize_label(txt):
                    return val

            raise ValueError(
                f"'{label}' ei leitud muutujas {variable_code}. "
                f"Näiteid: {[p[0] for p in pairs[:40]]}"
            )

    raise ValueError(f"Muutujat {variable_code} ei leitud metadata sees.")

def get_single_age_pairs(meta: dict, age_var_code: str) -> list[tuple[int, str]]:
    for var in meta["variables"]:
        if var["code"] == age_var_code:
            pairs = []
            for code, txt in zip(var["values"], var["valueTexts"]):
                txt_norm = normalize_label(txt)
                if txt_norm.isdigit():
                    age = int(txt_norm)
                    pairs.append((age, code))
            return sorted(pairs, key=lambda x: x[0])
    raise ValueError(f"Vanuse muutujat {age_var_code} ei leitud.")

def melt_wide_time_age(df: pd.DataFrame) -> pd.DataFrame:
    id_cols = [c for c in df.columns if not re.search(r"\d{4}\s+.+", c)]
    value_cols = [c for c in df.columns if c not in id_cols]

    long_df = df.melt(
        id_vars=id_cols,
        value_vars=value_cols,
        var_name="time_key",
        value_name="value"
    )

    extracted = long_df["time_key"].str.extract(r"(\d{4})\s+(.+)")
    long_df["year"] = pd.to_numeric(extracted[0], errors="coerce")
    long_df["subkey"] = extracted[1]
    long_df["value"] = pd.to_numeric(long_df["value"], errors="coerce")

    long_df = long_df.dropna(subset=["year", "value"]).copy()
    long_df["year"] = long_df["year"].astype(int)
    return long_df

def ensure_columns(df: pd.DataFrame, cols: list[int], fill_value: float = 0.0) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = fill_value
    return out[sorted(out.columns)]

def pivot_year_age(df_long: pd.DataFrame, age_col: str = "age") -> pd.DataFrame:
    return (
        df_long.pivot_table(index="year", columns=age_col, values="value", aggfunc="sum")
        .sort_index()
    )

def year_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if re.fullmatch(r"\d{4}", str(c))]

def linear_tfr_path(start_tfr: float, years: list[int], target_year: int = 2050, target_tfr: float = 1.63) -> dict:
    out = {}
    start_year = years[0]
    for y in years:
        if y >= target_year:
            out[y] = target_tfr
        else:
            frac = (y - start_year) / (target_year - start_year)
            out[y] = start_tfr + frac * (target_tfr - start_tfr)
    return out

def constant_tfr_path(level: float, years: list[int]) -> dict:
    return {y: level for y in years}

def declining_tfr_path(start_tfr: float, years: list[int], end_year: int = 2035, end_tfr: float = 1.00) -> dict:
    out = {}
    start_year = years[0]
    for y in years:
        if y >= end_year:
            out[y] = end_tfr
        else:
            frac = (y - start_year) / (end_year - start_year)
            out[y] = start_tfr + frac * (end_tfr - start_tfr)
    return out

def safe_mean(values, default=0.0):
    vals = [v for v in values if pd.notna(v)]
    return float(np.mean(vals)) if vals else float(default)

def parse_agegroup_range(label: str):
    txt = normalize_label(label)
    m = re.match(r"(\d+)\s*-\s*(\d+)", txt)
    if m:
        return int(m.group(1)), int(m.group(2))
    if txt.isdigit():
        a = int(txt)
        return a, a
    if "ja vanem" in txt:
        m2 = re.match(r"(\d+)", txt)
        if m2:
            return int(m2.group(1)), None
    return None

def find_matching_column(columns, patterns):
    for c in columns:
        cn = normalize_label(c)
        if all(p in cn for p in patterns):
            return c
    return None

def extract_annual_series_from_stat_df(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """
    Teisendab Statistikaameti vastuse kujule:
    year | <value_name>

    Toetab:
    1) veerud kujul: Aasta + numbrilised väärtusveerud
    2) veerud kujul: 2018, 2019, ...
    3) veerud kujul: 2018 Poisid ja tüdrukud, 2019 Poisid ja tüdrukud, ...
    """
    tmp = df.copy()
    tmp.columns = [clean_colname(c) for c in tmp.columns]

    # Variant A: olemas eraldi aasta veerg
    year_col = None
    for c in tmp.columns:
        if normalize_label(c) == "aasta":
            year_col = c
            break

    if year_col is not None:
        non_year_cols = [c for c in tmp.columns if c != year_col]

        numeric_candidates = []
        for c in non_year_cols:
            s = pd.to_numeric(tmp[c], errors="coerce")
            if s.notna().sum() > 0:
                numeric_candidates.append(c)

        if len(numeric_candidates) >= 1:
            out = tmp[[year_col] + numeric_candidates].copy()
            out[year_col] = pd.to_numeric(out[year_col], errors="coerce")
            for c in numeric_candidates:
                out[c] = pd.to_numeric(out[c], errors="coerce")

            out = out.dropna(subset=[year_col]).copy()
            out["year"] = out[year_col].astype(int)
            out[value_name] = out[numeric_candidates].sum(axis=1)

            return out[["year", value_name]].groupby("year", as_index=False)[value_name].sum()

    # Variant B: veerud algavad aastaga, nt "2018" või "2018 Poisid ja tüdrukud"
    year_like_cols = []
    for c in tmp.columns:
        if re.match(r"^\d{4}\b", str(c).strip()):
            year_like_cols.append(c)

    if len(year_like_cols) > 0:
        id_cols = [c for c in tmp.columns if c not in year_like_cols]

        long_df = tmp.melt(
            id_vars=id_cols,
            value_vars=year_like_cols,
            var_name="year_raw",
            value_name=value_name
        )

        long_df["year"] = long_df["year_raw"].astype(str).str.extract(r"^(\d{4})")[0]
        long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce")
        long_df[value_name] = pd.to_numeric(long_df[value_name], errors="coerce")

        long_df = long_df.dropna(subset=["year", value_name]).copy()
        long_df["year"] = long_df["year"].astype(int)

        return long_df.groupby("year", as_index=False)[value_name].sum()

    raise ValueError(f"Ei suutnud tabelist aastaseeriat välja lugeda. Veerud: {tmp.columns.tolist()}")
# =========================================================
# 1) RV0240 - RAHVASTIK
# =========================================================
print("1/12 Loen RV0240 metadata...")

meta_pop = get_metadata(TABLE_POP)

var_sex_pop = get_var(meta_pop, ["Sugu"])
var_place_pop = get_var(meta_pop, ["Elukoht"])
var_year_pop = get_var(meta_pop, ["Aasta"])
var_age_pop = get_var(meta_pop, ["Vanus"])

sex_m_code = get_value_code(meta_pop, var_sex_pop, "Mehed")
sex_f_code = get_value_code(meta_pop, var_sex_pop, "Naised")
place_code_pop = get_value_code(meta_pop, var_place_pop, MUNICIPALITY_LABEL)

single_age_pairs_pop = get_single_age_pairs(meta_pop, var_age_pop)
single_ages_pop = [age for age, code in single_age_pairs_pop]

print("RV0240 üksikvanuseid leitud:", len(single_age_pairs_pop))
print("Min vanus:", min(single_ages_pop), "Max vanus:", max(single_ages_pop))

def fetch_population_for_sex(sex_code: str) -> pd.DataFrame:
    parts = []
    chunk_size = 10
    age_chunks = [single_age_pairs_pop[i:i + chunk_size] for i in range(0, len(single_age_pairs_pop), chunk_size)]

    for y in POP_HISTORY_YEARS:
        for chunk in age_chunks:
            age_codes_chunk = [code for age, code in chunk]
            age_values_chunk = [age for age, code in chunk]

            print(f"RV0240: sugu={sex_code}, aasta={y}, vanused={age_values_chunk[0]}-{age_values_chunk[-1]}")

            query = [
                {"code": var_sex_pop, "selection": {"filter": "item", "values": [sex_code]}},
                {"code": var_place_pop, "selection": {"filter": "item", "values": [place_code_pop]}},
                {"code": var_year_pop, "selection": {"filter": "item", "values": [str(y)]}},
                {"code": var_age_pop, "selection": {"filter": "item", "values": age_codes_chunk}},
            ]

            raw = px_post_csv(TABLE_POP, query, debug_name=f"RV0240 year={y} ages={age_values_chunk[0]}-{age_values_chunk[-1]}")
            parts.append(raw)
            time.sleep(REQUEST_SLEEP)

    raw_all = pd.concat(parts, ignore_index=True)
    long_df = melt_wide_time_age(raw_all)
    long_df["age"] = pd.to_numeric(long_df["subkey"], errors="coerce")
    long_df = long_df.dropna(subset=["age"]).copy()
    long_df["age"] = long_df["age"].astype(int)

    pivot = pivot_year_age(long_df, age_col="age")
    pivot = ensure_columns(pivot, single_ages_pop, fill_value=0.0)
    return pivot

print("2/12 Loen RV0240 meeste andmed...")
pop_m = fetch_population_for_sex(sex_m_code)

print("3/12 Loen RV0240 naiste andmed...")
pop_f = fetch_population_for_sex(sex_f_code)

pop_both = pop_m.add(pop_f, fill_value=0.0)
BASE_YEAR = int(pop_both.index.max())
MAX_AGE = max(single_ages_pop)
AGES_ALL = list(range(min(single_ages_pop), MAX_AGE + 1))

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

# =========================================================
# 3) RV172 - SÜNDIMUSE VANUSKORDAJAD
# =========================================================
print("5/12 Loen RV172 sündimuse vanuskordajad...")

meta_asfr = get_metadata(TABLE_ASFR)
var_year_asfr = get_var(meta_asfr, ["Aasta"])
var_indicator_asfr = get_var(meta_asfr, ["Näitaja"])

indicator_obj = [v for v in meta_asfr["variables"] if v["code"] == var_indicator_asfr][0]
year_obj_asfr = [v for v in meta_asfr["variables"] if v["code"] == var_year_asfr][0]

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

available_asfr_years = [y for y in year_obj_asfr["values"] if 2015 <= int(y) <= 2024]

query_asfr = [
    {"code": var_year_asfr, "selection": {"filter": "item", "values": available_asfr_years}},
    {"code": var_indicator_asfr, "selection": {"filter": "item", "values": list(wanted_groups.values())}},
]

asfr_raw = px_post_csv(TABLE_ASFR, query_asfr, debug_name="RV172")

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

asfr_df = asfr_raw.rename(columns=rename_map).copy()
required_cols = ["year", "15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "15-49_total"]

asfr_df["year"] = pd.to_numeric(asfr_df["year"], errors="coerce")
for c in required_cols[1:]:
    asfr_df[c] = pd.to_numeric(asfr_df[c], errors="coerce") / 1000.0

asfr_df = asfr_df.dropna(subset=["year"]).copy()
asfr_df["year"] = asfr_df["year"].astype(int)
asfr_df = asfr_df.sort_values("year")
asfr_pivot = asfr_df.set_index("year")[required_cols[1:]].copy()

recent_asfr_year = int(asfr_pivot.index.max())
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

print("Viimane teadaolev TFR RV172 põhjal:", round(tfr_recent, 4))

TFR_SCENARIOS = {
    "stat_amet": linear_tfr_path(
        start_tfr=tfr_recent,
        years=FORECAST_YEARS,
        target_year=2050,
        target_tfr=TFR_TARGET_2050
    ),
    "praegune_tase": constant_tfr_path(
        level=tfr_recent,
        years=FORECAST_YEARS
    ),
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
print("6/12 Loen RV112U sündide andmed...")

meta_births = get_metadata(TABLE_BIRTHS)
var_year_births = get_var(meta_births, ["Aasta"])
var_place_births = get_var(meta_births, ["Haldusüksus", "Asustuspiirkonna", "Haldusüksus/ asustuspiirkonna liik"])
var_sex_births = get_var(meta_births, ["Sugu"])

place_code_births = get_value_code(meta_births, var_place_births, MUNICIPALITY_LABEL)
sex_both_births = get_value_code(meta_births, var_sex_births, "Poisid ja tüdrukud")

year_obj_births = [v for v in meta_births["variables"] if v["code"] == var_year_births][0]
available_birth_years = [y for y in year_obj_births["values"] if 2018 <= int(y) <= 2024]

query_births = [
    {"code": var_year_births, "selection": {"filter": "item", "values": available_birth_years}},
    {"code": var_place_births, "selection": {"filter": "item", "values": [place_code_births]}},
    {"code": var_sex_births, "selection": {"filter": "item", "values": [sex_both_births]}},
]

births_raw = px_post_csv(TABLE_BIRTHS, query_births, debug_name="RV112U")
births_hist_df = extract_annual_series_from_stat_df(births_raw, "births")
actual_births = births_hist_df.set_index("year")["births"].to_dict()


print("Rakvere valla sünnid:")
print(births_hist_df)

# =========================================================
# 4b) RV49U - SURMAD
# =========================================================
print("7/12 Loen RV49U surmade andmed...")

meta_deaths = get_metadata(TABLE_DEATHS)
var_year_deaths = get_var(meta_deaths, ["Aasta"])
var_place_deaths = get_var(meta_deaths, ["Haldusüksus", "Asustuspiirkonna", "Haldusüksus/ asustuspiirkonna liik"])
var_sex_deaths = get_var(meta_deaths, ["Sugu"])

place_code_deaths = get_value_code(meta_deaths, var_place_deaths, MUNICIPALITY_LABEL)

try:
    sex_both_deaths = get_value_code(meta_deaths, var_sex_deaths, "Mehed ja naised")
except ValueError:
    sex_both_deaths = get_value_code(meta_deaths, var_sex_deaths, "Kokku")

year_obj_deaths = [v for v in meta_deaths["variables"] if v["code"] == var_year_deaths][0]
available_death_years = [y for y in year_obj_deaths["values"] if 2018 <= int(y) <= 2024]

query_deaths = [
    {"code": var_year_deaths, "selection": {"filter": "item", "values": available_death_years}},
    {"code": var_place_deaths, "selection": {"filter": "item", "values": [place_code_deaths]}},
    {"code": var_sex_deaths, "selection": {"filter": "item", "values": [sex_both_deaths]}},
]

deaths_raw = px_post_csv(TABLE_DEATHS, query_deaths, debug_name="RV49U")
deaths_hist_df = extract_annual_series_from_stat_df(deaths_raw, "deaths")
actual_deaths = deaths_hist_df.set_index("year")["deaths"].to_dict()

print("Rakvere valla surmad:")
print(deaths_hist_df)

# =========================================================
# 5) KOHALIK SÜNDIMUSE KORRIGEERIMISTEGUR
# =========================================================
print("8/12 Arvutan Rakvere kohaliku sündimuse korrigeerimisteguri...")

local_fertility_factors = []
for y in [yr for yr in [2022, 2023, 2024] if yr in pop_f.index and yr in asfr_pivot.index and yr in actual_births]:
    women_y = pop_f.loc[y].astype(float)
    model_births = 0.0
    for grp, ages in ASFR_GROUPS.items():
        women_in_group = float(women_y[ages].sum())
        rate = float(asfr_pivot.loc[y, grp])
        model_births += women_in_group * rate

    actual_y = float(actual_births[y])
    if model_births > 0:
        local_fertility_factors.append(actual_y / model_births)

local_fertility_factor = safe_mean(local_fertility_factors, default=1.0)
print("Rakvere kohaliku sündimuse korrigeerimistegur:", round(local_fertility_factor, 4))

# =========================================================
# 6) RVR02 - RÄNDE SALDO
# =========================================================
print("9/12 Loen RVR02 rände saldo andmed...")

meta_mig_muni = get_metadata(TABLE_MIG_MUNI)
var_year_mig_muni = get_var(meta_mig_muni, ["Aasta"])
var_place_mig_muni = get_var(meta_mig_muni, ["Haldusüksus", "Asustuspiirkonna"])

place_code_mig = get_value_code(meta_mig_muni, var_place_mig_muni, MUNICIPALITY_LABEL)

query_mig_muni = [
    {"code": var_year_mig_muni, "selection": {"filter": "item", "values": [str(y) for y in range(2015, 2025)]}},
    {"code": var_place_mig_muni, "selection": {"filter": "item", "values": [place_code_mig]}},
]

mig_muni_raw = px_post_csv(TABLE_MIG_MUNI, query_mig_muni, debug_name="RVR02")

year_col = find_matching_column(mig_muni_raw.columns, ["aasta"])
in_col = find_matching_column(mig_muni_raw.columns, ["rändesaldo", "siser"])
out_col = find_matching_column(mig_muni_raw.columns, ["rändesaldo", "välis"])

if year_col is None or in_col is None or out_col is None:
    raise ValueError(f"RVR02 veergude tuvastamine ebaõnnestus. Veerud: {mig_muni_raw.columns.tolist()}")

mig_muni_df = mig_muni_raw[[year_col, in_col, out_col]].copy()
mig_muni_df.columns = ["year", "sisserande_saldo", "valisrande_saldo"]
mig_muni_df["year"] = pd.to_numeric(mig_muni_df["year"], errors="coerce")
mig_muni_df["sisserande_saldo"] = pd.to_numeric(mig_muni_df["sisserande_saldo"], errors="coerce")
mig_muni_df["valisrande_saldo"] = pd.to_numeric(mig_muni_df["valisrande_saldo"], errors="coerce")
mig_muni_df = mig_muni_df.dropna(subset=["year"]).copy()
mig_muni_df["year"] = mig_muni_df["year"].astype(int)
mig_muni_df["kokku_netosaldo"] = mig_muni_df["sisserande_saldo"] + mig_muni_df["valisrande_saldo"]

in_mig_hist = mig_muni_df.set_index("year")["sisserande_saldo"]
out_mig_hist = mig_muni_df.set_index("year")["valisrande_saldo"]
total_net_hist = mig_muni_df.set_index("year")["kokku_netosaldo"]

avg_net_migration_total = float(total_net_hist.loc[MIG_HISTORY_YEARS].mean()) if set(MIG_HISTORY_YEARS).issubset(set(total_net_hist.index)) else float(total_net_hist.mean())
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
    net_migration_age_shape[:] = 0.0
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
recent_group_rates = asfr_pivot.loc[recent_asfr_year, list(ASFR_GROUPS.keys())].astype(float).copy()
group_shape = recent_group_rates / recent_group_rates.sum()

female_share_by_age = (
    pop_f.loc[BASE_YEAR, FERTILE_AGES] /
    pop_both.loc[BASE_YEAR, FERTILE_AGES].replace(0, np.nan)
).fillna(0.5)

population_rows = []
birth_rows = []
kinder_rows = []

avg_annual_net_migration = float(total_net_hist.loc[MIG_HISTORY_YEARS].mean()) if set(MIG_HISTORY_YEARS).issubset(set(total_net_hist.index)) else float(total_net_hist.mean())

for fertility_scenario, tfr_path in TFR_SCENARIOS.items():
    for migration_scenario in ["ilma_randeta", "randega"]:

        pop_prev = pop_both.loc[BASE_YEAR, AGES_ALL].astype(float).copy()

        for year in FORECAST_YEARS:
            if migration_scenario == "randega":
                annual_mig_vector = net_migration_age_shape * avg_annual_net_migration
            else:
                annual_mig_vector = pd.Series(0.0, index=AGES_ALL, dtype=float)

            deaths_by_age = pop_prev * mortality_rate
            total_deaths = float(deaths_by_age.sum())

            survivors = pop_prev - deaths_by_age
            survivors = survivors.clip(lower=0.0)

            next_pop = pd.Series(0.0, index=AGES_ALL, dtype=float)
            for age in range(1, MAX_AGE):
                next_pop.loc[age] = float(survivors.loc[age - 1])

            next_pop.loc[MAX_AGE] = float(survivors.loc[MAX_AGE - 1]) + float(survivors.loc[MAX_AGE])

            next_pop = next_pop.add(annual_mig_vector, fill_value=0.0)
            next_pop = next_pop.clip(lower=0.0)

            women_current = (next_pop[FERTILE_AGES] * female_share_by_age).astype(float)

            tfr_y = tfr_path[year]
            group_rates_future = group_shape * (tfr_y / 5.0)

            births_national_pattern = 0.0
            for grp, ages in ASFR_GROUPS.items():
                women_in_group = float(women_current[ages].sum())
                births_national_pattern += women_in_group * float(group_rates_future[grp])

            births_local = births_national_pattern * local_fertility_factor

            next_pop.loc[0] = max(0.0, births_local + float(annual_mig_vector.loc[0]))

            total_population_prev = float(pop_prev.sum())
            total_population = float(next_pop.sum())
            migration_total = float(annual_mig_vector.sum())
            natural_increase = births_local - total_deaths

            scenario_name = f"{fertility_scenario}_{migration_scenario}"

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

            if year in KINDER_YEARS:
                total_need = sum(next_pop[a] * PARTICIPATION_BY_AGE[a] for a in ALL_KINDER_AGES if a in next_pop.index)
                small_need = sum(next_pop[a] * PARTICIPATION_BY_AGE[a] for a in SMALL_CHILD_AGES if a in next_pop.index)

                diff_total = total_need - TOTAL_KINDER_PLACES
                diff_small = small_need - PLACES_15_TO_3

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
                    "vanus_1": round(float(next_pop.get(1, 0)), 2),
                    "vanus_2": round(float(next_pop.get(2, 0)), 2),
                    "vanus_3": round(float(next_pop.get(3, 0)), 2),
                    "vanus_4": round(float(next_pop.get(4, 0)), 2),
                    "vanus_5": round(float(next_pop.get(5, 0)), 2),
                    "vanus_6": round(float(next_pop.get(6, 0)), 2),
                    "lasteaiaealised_1_6": round(sum(float(next_pop.get(a, 0)) for a in ALL_KINDER_AGES), 2),
                    "vajalikud_kohad_kokku": round(total_need, 2),
                    "olemasolevad_kohad_kokku": TOTAL_KINDER_PLACES,
                    "puudu_voi_ule_kokku": round(diff_total, 2),
                    "uusi_kohti_vaja_kokku": max(0, math.ceil(diff_total)),
                    "vajalikud_kohad_1_5_3_ligikaudne": round(small_need, 2),
                    "olemasolevad_kohad_1_5_3": PLACES_15_TO_3,
                    "puudu_voi_ule_1_5_3": round(diff_small, 2),
                    "uusi_kohti_vaja_1_5_3": max(0, math.ceil(diff_small)),
                })

            if DEBUG_FORECAST and year <= 2030:
                print(
                    f"{scenario_name} | {year} | "
                    f"P={round(total_population,1)} | "
                    f"B={round(births_local,1)} | "
                    f"D={round(total_deaths,1)} | "
                    f"M={round(migration_total,1)}"
                )

            pop_prev = next_pop.copy()

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
population_df.to_csv("rakvere_rahvastiku_prognoos_2026_2035.csv", index=False, encoding="utf-8-sig")
birth_forecast_df.to_csv("rakvere_synnid_2026_2035.csv", index=False, encoding="utf-8-sig")
kinder_df.to_csv("rakvere_lasteaiavajadus_2026_2030.csv", index=False, encoding="utf-8-sig")
summary_table.to_csv("rakvere_kokkuvottev_tabel.csv", index=False, encoding="utf-8-sig")
yearly_compare_table.to_csv("rakvere_aastate_vordlus_tabel.csv", encoding="utf-8-sig")
population_compare_table.to_csv("rakvere_rahvaarvu_vordlus_tabel.csv", encoding="utf-8-sig")
migration_plot_df.to_csv("rakvere_rande_saldo_2015_2024.csv", index=False, encoding="utf-8-sig")
birth_death_hist_df.to_csv("rakvere_synnid_surmad_2018_2024.csv", index=False, encoding="utf-8-sig")

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
plt.savefig("rakvere_rande_saldo_2015_2024.png", dpi=200)
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
plt.savefig("rakvere_synnid_surmad_2018_2024.png", dpi=200)
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
plt.savefig("rakvere_synnid_2026_2035.png", dpi=200)
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
plt.savefig("rakvere_synnid_surmad_prognoos_2026_2035.png", dpi=200)
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
plt.savefig("rakvere_lasteaiakohad_2026_2030.png", dpi=200)
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
plt.savefig("rakvere_rahvaarvu_prognoos_2026_2035.png", dpi=200)
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