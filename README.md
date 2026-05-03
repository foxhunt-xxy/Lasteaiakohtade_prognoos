# Rakvere valla sündivuse ja rände trendide analüüs lasteaia kohtade vajaduse hindamiseks

## Uurimisküsimus

Kuidas on muutunud Rakvere valla sündivus ja ränne ning mida see tähendab lasteaia kohtade vajaduse jaoks lähiaastatel?

---

## Projekti eesmärk

Projekti eesmärk on luua **täielik ETL-pipeline**, mis:

* loeb Statistikaameti API-st rahvastiku-, sündide-, surmade- ja rändeandmeid
* puhastab ja teisendab need analüüsitavaks kujuks
* salvestab tulemused PostgreSQL andmebaasi
* võimaldab tulemusi visualiseerida Apache Supersetis

---

## Arhitektuur

```text
Statistikaameti API
        ↓
Python ETL (Lasteaiakohad.py)
        ↓
CSV väljundfailid (Outputs/)
        ↓
PostgreSQL (etl/load_to_postgres.py)
        ↓
Apache Superset
        ↓
Dashboard ja visualiseeringud
```

---

## Andmeallikad

Statistikaameti API tabelid:

* RV0240 – rahvastik soo, vanuse ja elukoha järgi
* RV112U – elussündinud soo ja haldusüksuse järgi
* RV49U – surnud soo ja haldusüksuse järgi
* RV172 – sündimuse vanuskordajad
* RVR02 – rände saldo haldusüksuse järgi
* RVR03 – rände saldo vanuserühma järgi

---

## Projekti struktuur

```text
.
├── Outputs/                     # genereeritud CSV ja pildid
├── etl/
│   └── load_to_postgres.py     # Load: CSV → PostgreSQL
├── docker/
│   └── superset/
│       └── Dockerfile          # Superset + PostgreSQL driver
├── Lasteaiakohad.py            # ETL + prognoos + graafikud
├── docker-compose.yml          # PostgreSQL + Superset
├── requirements.txt
└── README.md
```

---

## Projekti käivitamine

NB! Projektis kasutatakse kahte erinevat terminali:

* Python/ETL käsud võib käivitada VS Code devcontaineri terminalis.
* Docker Compose käsud tuleb praeguses seadistuses käivitada host-arvuti terminalis, näiteks Windows PowerShellis, sest devcontaineris ei ole `docker` käsk saadaval.

Windows PowerShellis liigu projekti juurkausta ehk kausta, kus asub docker-compose.yml.


### 1. Paigalda Python sõltuvused

```bash
pip install -r requirements.txt
```

---

### 2. Käivita PostgreSQL ja Superset

Käivita Docker Compose host-arvuti terminalis, näiteks Windows PowerShellis projekti juurkaustas:

```powershell
docker compose up -d
```

Kontrolli, kas teenused töötavad:

```powershell
docker compose ps
```

Oodatav tulemus on, et `lasteaiakohad_postgres` ja `lasteaiakohad_superset` on üleval. Host-arvutis kasutab PostgreSQL porti `5433` ja Superset porti `8089`.

---

### 3. Käivita ETL pipeline

```bash
python Lasteaiakohad.py
```

See samm:

* laeb andmed API-st
* teeb transformatsioonid
* arvutab prognoosid
* salvestab CSV failid ja graafikud kausta `Outputs/`

---

### 4. Lae andmed PostgreSQL-i

Kui käivitad käsu host-arvuti terminalis, näiteks Windows PowerShellis, kasuta:

```powershell
python etl/load_to_postgres.py
```

Kui käivitad käsu VS Code devcontaineri terminalis, kasuta:

```bash
DB_URL="postgresql+psycopg2://postgres:postgres@host.docker.internal:5433/lasteaiakohad" python etl/load_to_postgres.py
```

`load_to_postgres.py` loeb andmebaasi aadressi `DB_URL` keskkonnamuutujast. Kui `DB_URL` ei ole määratud, kasutatakse vaikimisi ühendust `localhost:5433`, mis sobib host-arvuti terminalist käivitamiseks.

---

### 5. Ava Superset

Brauseris:

```text
http://localhost:8089
```

**Login:**

* kasutaja: `admin`
* parool: `admin`

---

### 6. Lisa PostgreSQL ühendus Supersetis

Connection string:

```text
postgresql+psycopg2://postgres:postgres@postgres:5432/lasteaiakohad
```

Kui Superset küsib ühenduse andmeid eraldi väljadena, kasuta:

* Host: `postgres`
* Port: `5432`
* Database name: `lasteaiakohad`
* Username: `postgres`
* Password: `postgres`

NB:

* Superseti kasutaja `admin/admin` on Superseti veebiliidese jaoks.
* PostgreSQL kasutaja on `postgres/postgres`.
* Superseti sees on PostgreSQL host `postgres`, sest mõlemad teenused töötavad samas Docker Compose võrgus.
* Kui ühendud PostgreSQL-iga otse host-arvutist, kasuta porti `5433`.

---

### 7. Kontrolli ühendust SQL Labis

Supersetis ava SQL Lab ja käivita kontrollpäring:

```sql
SELECT * FROM summary LIMIT 10;

#Kõigi tabelite kontrollimiseks:
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public'
ORDER BY table_name;
```

---

## PostgreSQL tabelid

ETL loob järgmised tabelid:

* `population_forecast`
* `birth_forecast`
* `kinder_need`
* `summary`
* `yearly_kinder_compare`
* `population_compare`
* `migration_history`
* `birth_death_history`
* `population_pyramid`

---

## Visualiseerimine (Superset)

Dashboard sisaldab:

* Rahvaarvu prognoos (2026–2035)
* Sündide ja surmade trendid
* Rände saldo
* Lasteaiakohtade vajadus
* Rahvastikupüramiid

---


## Peamised järeldused

* Rahvaarv väheneb enamikus stsenaariumites
* Loomulik iive on negatiivne
* Ränne mõjutab tulevikuprognoosi oluliselt
* Lasteaiakohtade vajadus pigem väheneb

---

## Piirangud

* Prognoos põhineb eeldustel ja ajaloolistel trendidel
* Rände vanuseline jaotus on lihtsustatud
* Ei eristata era- ja munitsipaallasteaedu
* Laste osalemismäärad on hinnangulised

---

## Kasutatud tehnoloogiad

* Python (pandas, numpy, requests, matplotlib)
* SQLAlchemy
* PostgreSQL
* Docker Compose
* Apache Superset

---

## Autorid

Jaak Ilves, Kata Metsar, Liis Lille, Miina Voltri
Andmetehnika projekt