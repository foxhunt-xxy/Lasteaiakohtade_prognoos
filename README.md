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
# Käivita Docker Engine

Enne Docker Compose käivitamist peab töötama Docker Engine ehk Docker Desktop.

## Windowsis:

1. Ava Docker Desktop
2. Oota kuni kuvatakse:

```text
Engine running
```

või

```text
Docker Desktop is running
```

### 0. Projekti avamine

1. Ava Visual Studio Code

2. Logi sisse GitHubi (kui ei ole juba sisse logitud)

3. Klooni projekt:
   - vajuta **"Clone Repository"**
   - vali projekti repo nimekirjast või kasuta repo URL-i (nt GitHubist kopeeritud link)

   Kui projekt on juba arvutis olemas, vali lihtsalt **"Open Folder"** ja ava see kaust
  
4. Ava projekt Dev Containeris:
   - VS Code pakub tavaliselt automaatselt **"Reopen in Container"**
   - kui ei paku, vajuta:
     ```
     Ctrl + Shift + P → Reopen in Container
     ```

NB:
- Dev Container loob valmis keskkonna, kus kõik vajalikud tööriistad on juba paigaldatud
- Projekti on võimalik käivitada ka ilma Dev Containerita (nt otse oma arvutis), kuid sel juhul võivad olla vajalikud lisaseadistused (Python, pip jne)

### 1. Paigalda Python sõltuvused

```bash
pip install -r requirements.txt
```
NB:

- Kui `pip` ei tööta, kasuta:
  ```bash
  python -m pip install -r requirements.txt

  Kui kasutad Dev Containerit, võivad sõltuvused olla juba paigaldatud
---

### 2. Käivita PostgreSQL ja Superset (Dockeriga)

Käivita Docker Compose host-arvuti terminalis, näiteks Windows PowerShellis projekti juurkaustas:

```powershell
docker compose up -d
```
NB:

- Esmakordsel käivitamisel võib minna kuni ~30 sekundit, enne kui teenused on valmis

- Kontrollimiseks:
  ```bash
  docker ps

Kontrolli, kas teenused töötavad:

```powershell
docker compose ps
```

Oodatav tulemus on, et `lasteaiakohad_postgres` ja `lasteaiakohad_superset` on üleval. Host-arvutis kasutab PostgreSQL porti `5433` ja Superset porti `8089`.

  Oota kuni lasteaiakohad_superset container on olekus (healthy)
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

Skripti lõpuni töötamiseks peab lahti hüpanud aknad graafikutega sulgema.

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

NB:
- Mõnes konfiguratsioonis jookseb Superset pordil **8089**, sel juhul kasuta: http://localhost:8089/
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
* Superseti sees on host `postgres`
* Kui ühendud otse arvutist (nt DBeaver vms), kasuta porti `5433`

- Kui ühendus ei tööta:
- veendu, et Docker containerid töötavad:
  ```bash
  docker ps
  ```
- kontrolli, et `lasteaiakohad_superset` on olekus `(healthy)`
- vajadusel tee:
  ```bash
  docker compose restart superset
  ```
---
- Mõnel juhul võib olla vajalik PostgreSQL driveri lubamine Supersetis (see on projektis juba seadistatud Dockerfile kaudu)

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