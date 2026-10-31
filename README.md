# Smart Transit & Crowdsourcing Engine — Bakı

Bakı avtobus şəbəkəsi üçün funksional prototip. İki ayrı tətbiqdən ibarətdir:

| Tətbiq | Ünvan | Nə edir |
|---|---|---|
| **Sərnişin** | http://localhost:3000 | Xətt və ya dayanacaq seçəndə avtobusların canlı mövqeyi və gəliş vaxtı (ETA); sıxlıq bildirişi göndərmək |
| **Operator paneli** | http://localhost:3001 | Xətlər üzrə sıxlıq xəritəsi və siyahısı; xətt 10 dəqiqə "Yüksək" qalanda **"Əlavə avtobus ehtiyatı ayrılmalıdır"** bildirişi və avtobus yönləndirmə |
| Backend API | http://localhost:8000/docs | FastAPI, hər iki tətbiqin datası |

- **Real şəbəkə:** 208 xətt, 3 450 dayanacaq və yol həndəsəsi — [map.ayna.gov.az](https://map.ayna.gov.az/) ictimai API-sindən.
- **Simulyasiya edilmiş canlı data:** avtobusların GPS-i, sərnişin sayı və sərnişin bildirişləri simulyatorla yaradılır.

---

## Tələblər

| Proqram | Versiya | Yoxlamaq üçün |
|---|---|---|
| [Git](https://git-scm.com/downloads) | istənilən | `git --version` |
| [Python](https://www.python.org/downloads/) | **3.11 və ya daha yeni** (3.12 tövsiyə olunur) | `python --version` (macOS/Linux: `python3 --version`) |
| [Node.js](https://nodejs.org/) | **20 və ya daha yeni** (LTS) | `node --version` |

İnternet lazımdır: paketləri yükləmək və xəritə plitələri (OpenStreetMap) üçün.

---

## Quraşdırma və işə salma

Üç terminal pəncərəsi lazım olacaq: **backend**, **sərnişin tətbiqi**, **operator tətbiqi**.
Aşağıdakı əmrləri **sıra ilə** yazın.

### Addım 1 — Layihəni yükləyin

```bash
git clone https://github.com/resullhuseynli/hackaton-aztu.git
cd hackaton-aztu
```

### Addım 2 — Backend (1-ci terminal)

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m app.seed
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

**macOS / Linux:**

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.seed
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Nə baş verir:

1. `python -m venv .venv` — layihəyə aid Python mühiti yaradır (sistemə heç nə quraşdırılmır).
2. `pip install -r requirements.txt` — FastAPI və uvicorn-u həmin mühitə quraşdırır.
3. `python -m app.seed` — `backend/sources/bus_lines.json` faylından verilənlər bazasını
   (`backend/database/transport.db`) qurur. Təxminən 10 saniyə çəkir, internet tələb etmir.
4. `uvicorn ...` — API-ni işə salır. Terminalda `Uvicorn running on http://127.0.0.1:8000` görünəndə hazırdır.
   **Bu terminalı bağlamayın.**

Yoxlamaq üçün brauzerdə açın: http://localhost:8000/docs

### Addım 3 — Frontend paketləri (2-ci terminal, bir dəfə)

Layihənin kök qovluğundan (`hackaton-aztu`):

```bash
cd frontend
npm install
```

Bu, hər iki tətbiqin (sərnişin və operator) paketlərini birlikdə quraşdırır.

### Addım 4 — Sərnişin tətbiqi (2-ci terminal)

Eyni terminalda (`frontend` qovluğunda):

```bash
npm run dev:passenger
```

Açın: **http://localhost:3000**

### Addım 5 — Operator tətbiqi (3-cü terminal)

Yeni terminal açın və layihənin kök qovluğundan:

```bash
cd frontend
npm run dev:operator
```

Açın: **http://localhost:3001**

### Növbəti dəfə işə salmaq

Quraşdırma bir dəfəlikdir. Sonrakı dəfələrdə yalnız üç əmr lazımdır (hər biri öz terminalında):

```bash
# 1-ci terminal (Windows)          # 1-ci terminal (macOS/Linux)
cd backend                          cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
                                    .venv/bin/python -m uvicorn app.main:app --port 8000

# 2-ci terminal
cd frontend
npm run dev:passenger

# 3-cü terminal
cd frontend
npm run dev:operator
```

Datanı AYNA-dan yeniləmək istəsəniz (internet lazımdır, ~1 dəqiqə):
`.venv\Scripts\python -m app.seed --refresh` (macOS/Linux: `.venv/bin/python -m app.seed --refresh`).

---

## Testlər

Backend üçün 75 unit və inteqrasiya testi var (sıxlıq qaydaları, 10 dəqiqəlik xəbərdarlıq, ETA, AYNA
datasının idxalı, simulyator, HTTP API və WebSocket). Testlər öz kiçik test şəbəkəsini müvəqqəti bazada
qurur — əsas bazaya və internetə toxunmur.

```powershell
cd backend
.venv\Scripts\python -m pip install -r requirements-dev.txt     # bir dəfə (pytest)
.venv\Scripts\python -m pytest
```

macOS/Linux: `.venv/bin/python -m pip install -r requirements-dev.txt` və `.venv/bin/python -m pytest`.

Gözlənilən nəticə: `75 passed`.

| Fayl | Nəyi yoxlayır |
|---|---|
| `tests/test_rules.py` | Sıxlıq hədləri, bal düsturu, bildiriş çəkisi, pik saatlar, "10 dəqiqə ardıcıl" qaydası, ETA düsturu |
| `tests/test_geo.py` | Məsafə, marşrut üzrə yerləşdirmə, eyni yoldan iki dəfə keçən marşrutlar |
| `tests/test_ingestion.py` | AYNA datasının idxalı: tərs çəkilmiş və səhv xətlər, paylaşılan dayanacaqlar, avtobus parkı |
| `tests/test_analytics.py` | Xəbərdarlığın 10-cu dəqiqədə yaranması, təkrarlanmaması, avtomatik bağlanması, donor xətt |
| `tests/test_eta.py` | Gəliş vaxtı, keçilmiş dayanacaq, istiqamət, orta sürət |
| `tests/test_simulation.py` | Avtobusların hərəkəti, tutum həddi, sıxlaşdırma, yönləndirmə, təkrarlana bilən nəticə |
| `tests/test_api.py` | Bütün HTTP endpoint-lər, səhv sorğular, WebSocket və tam ssenari: sıxlaşdır → xəbərdarlıq → yönləndir |

---

## Konfiqurasiya

Backend (mühit dəyişənləri, `uvicorn` əmrindən əvvəl təyin edilir):

| Dəyişən | Default | Məna |
|---|---|---|
| `SIM_SPEED` | `10` | Simulyasiya sürəti: 1 real saniyə = 10 simulyasiya saniyəsi |
| `SIM_START` | `08:00` | Simulyasiyanın başlanğıc saatı (pik saatlar: 07:30–09:30, 17:30–19:30) |
| `TICK_SECONDS` | `1` | Simulyasiya addımı (real saniyə) |
| `SIM_SEED` | `42` | Təsadüfi ədədlər üçün toxum (eyni toxum = eyni nəticə) |

Nümunə — Windows: `$env:SIM_SPEED="20"; .venv\Scripts\python -m uvicorn app.main:app --port 8000`,
macOS/Linux: `SIM_SPEED=20 .venv/bin/python -m uvicorn app.main:app --port 8000`.

Frontend:

| Dəyişən | Default | Məna |
|---|---|---|
| `PORT` | `3000` (sərnişin), `3001` (operator) | Tətbiqin portu |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Backend ünvanı (`/api` və `/ws` buraya ötürülür) |

---

## Layihə strukturu

```
hackaton-aztu/
├── backend/
│   ├── app/
│   │   ├── controller/      HTTP + WebSocket endpoint-lər, Pydantic sxemləri
│   │   ├── business/        servislər: ETA, analitika, operator, sərnişin, simulyator, data idxalı
│   │   ├── domain/          modellər, enum-lar, qaydalar (rules.py), geometriya (geo.py)
│   │   ├── repository/      SQLite sorğuları və sxem (schema.sql)
│   │   ├── config.py        parametrlər
│   │   ├── container.py     servislərin bir-birinə bağlanması
│   │   ├── main.py          FastAPI tətbiqi
│   │   └── seed.py          bazanın qurulması (python -m app.seed)
│   ├── sources/bus_lines.json   AYNA-dan yüklənmiş şəbəkə
│   ├── database/            transport.db (seed ilə yaradılır, git-də saxlanmır)
│   ├── tests/               pytest testləri
│   ├── requirements.txt
│   └── requirements-dev.txt
└── frontend/                npm workspaces
    ├── shared/              ortaq kod: API klienti, xəritə, komponentlər, stillər
    ├── passenger/           sərnişin tətbiqi (port 3000)
    └── operator/            operator tətbiqi (port 3001)
```

## Arxitektura

```
Sərnişin tətbiqi (:3000)      Operator tətbiqi (:3001)
          │  REST /api/*  +  WebSocket /ws/live  │
          └──────────────────┬───────────────────┘
                     FastAPI backend (:8000)
   controller → business → domain / repository → SQLite
```

Qatlar yalnız aşağıya müraciət edir. Analitika və ETA datanı yalnız bazadan oxuyur, ona görə
simulyatoru real GPS, BakıKart və qapı sensoru inteqrasiyası ilə əvəz etmək qalan koda toxunmur.

### Verilənlər bazası

| Cədvəl | Məzmun |
|---|---|
| `lines` | Xətlər (nömrə, daşıyıcı, son dayanacaqlar, uzunluq, tarif) |
| `stops` | Dayanacaqlar (ad, ünvan, GPS) — paylaşılan dayanacaq bir dəfə saxlanır |
| `line_stops` | Xəttin istiqamət üzrə dayanacaq ardıcıllığı və marşrut üzrə məsafəsi |
| `route_shapes` | Xəttin yol həndəsəsi |
| `buses` | `line_id, bus_id, bus_plate, passenger_count, passenger_percentage, passenger_limit, forwarding_stop_id, live_longitude, live_latitude` + istiqamət, status, sürət |
| `bus_telemetry` | GPS və sərnişin sayı tarixçəsi (dəqiqəlik) |
| `crowd_reports` | Sərnişin bildirişləri |
| `line_density` | Xətt üzrə dəqiqəlik sıxlıq ölçmələri |
| `alerts` | Operator xəbərdarlıqları |

## Necə işləyir

### Sıxlıq balı (0–100)

```
doluluq       = xidmətdəki avtobusların orta doluluq faizi (passenger_count / passenger_limit)
bildiriş balı = son 10 dəqiqənin sərnişin bildirişlərinin ortası (Boşdur=25, Orta=65, Çox sıxdır=95)
çəki          = 0.3 × min(1, bildiriş sayı / 5)
bal           = (1 − çəki) × doluluq + çəki × bildiriş balı
```

Səviyyə: `< 50` Aşağı, `50–85` Orta, `> 85` Yüksək. Əsas mənbə avtobusun doluluğudur; bildirişlər ən çoxu
30% təsir edir və bir-iki səhv bildiriş nəticəni dəyişə bilmir. Terminalda fasilədə olan boş avtobuslar
ortalamaya daxil edilmir.

### Anomaliya xəbərdarlığı

- Hər simulyasiya dəqiqəsində bütün xətlər üçün bal hesablanır.
- Xətt son **10 dəqiqənin bütün ölçmələrində "Yüksək"** olubsa → "Əlavə avtobus ehtiyatı ayrılmalıdır".
- Tövsiyə olunan avtobus sayı balı 85-ə endirmək üçün lazım olan saydır (1–5).
- **Donor xətt:** 8 km radiusda ən boş "Aşağı" səviyyəli xətt.
- Operator "N avtobus yönləndir" ilə avtobusları köçürür və ya bildirişi bağlayır.
- Sıxlıq 5 dəqiqə ardıcıl "Yüksək"dən aşağı olsa, bildiriş avtomatik bağlanır.

### ETA

Avtobusdan dayanacağa qədər marşrut üzrə məsafə ÷ avtobusun son 5 dəqiqədəki orta hərəkət sürəti +
aradakı hər dayanacaq üçün 30 saniyə.

### Avtobusdakı sərnişin sayı: real data mənbələri

Sıxlığın əsas mənbəyi avtobusdakı sərnişin sayıdır (`buses.passenger_count`). Real sistemdə bu rəqəm iki
mənbədən hesablanır:

| Göstərici | Mənbə |
|---|---|
| **Minən sərnişinlər** | **BakıKart validasiyaları**: sərnişin kartı validatora toxundurduqca sayılır (hər toxunuş = 1 minən) |
| **Düşən sərnişinlər** | **Qapı sensorları**: avtobusun qapılarındakı sayğac sensorları çıxan sərnişinləri sayır |

```
passenger_count = əvvəlki say + BakıKart validasiyaları − qapı sensorlarının saydığı çıxanlar
                  (0-dan aşağı düşmür; son dayanacaqda sıfırlanır)
passenger_percentage = passenger_count / passenger_limit × 100
```

Avtobusun bort cihazı bu iki sayğacı GPS mövqeyi ilə birlikdə backend-ə göndərir və `buses` cədvəlini
yeniləyir. Analitika, ETA və hər iki tətbiq datanı yalnız bu cədvəldən oxuduğu üçün real inteqrasiyada
yalnız simulyator əvəz olunur, qalan kod dəyişmir.

> **Prototipdə** BakıKart və qapı sensoru datası yoxdur. Minən və düşən sərnişinləri simulyator yaradır və
> nəticəni eyni `passenger_count` sütununa yazır.

### Simulyator

- 1 797 avtobus real AYNA yolları ilə hərəkət edir; pik saatlarda sürət azalır.
- Sərnişinlər dayanacaqlara təsadüfi tempdə gəlir, avtobusa minir və düşür. Dayanacaqda gözləyənlərin
  sayı göstərilmir (real həyatda bu bilinmir), yalnız avtobusun doluluğuna təsir edir.
- Xətlərin ~8%-i həddən artıq dolu, ~15%-i az yüklüdür — tapşırıqdakı balanssızlıq.
- Sərnişin bildirişlərinin ~20%-i bilərəkdən səhvdir.

## API

| Metod | Endpoint | Məqsəd |
|---|---|---|
| GET | `/api/lines?q=` | Xətlər və cari sıxlıq |
| GET | `/api/lines/{id}` | Dayanacaqlar və yol həndəsəsi |
| GET | `/api/lines/{id}/buses` | Canlı avtobuslar, növbəti dayanacaq və ETA |
| GET | `/api/stops?q=` | Dayanacaq axtarışı |
| GET | `/api/stops/{id}` | Dayanacağa gələn avtobuslar (ETA) |
| POST | `/api/reports` | Sərnişin bildirişi `{line_id, level, stop_id?, bus_id?}` |
| GET | `/api/operator/overview` | Ümumi göstəricilər |
| GET | `/api/operator/density?level=` | Xətlər üzrə sıxlıq (ən sıx əvvəldə) |
| GET | `/api/operator/buses` | Bütün avtobuslar (sıxlıq xəritəsi) |
| GET | `/api/operator/density/{id}/history` | Xəttin sıxlıq tarixçəsi |
| GET | `/api/operator/alerts?status=` | Xəbərdarlıqlar |
| POST | `/api/operator/alerts/{id}/dispatch` | Donor xətdən avtobus yönləndir |
| POST | `/api/operator/alerts/{id}/resolve` | Xəbərdarlığı bağla |
| POST | `/api/demo/surge/{line_id}` | Demo: xətti 30 dəqiqəlik sıxlaşdır |
| GET | `/api/demo/simulation` | Simulyasiya saatı |
| WS | `/ws/live?line_id=&operator=true` | Hər 2 saniyədən bir canlı yeniləmə |

## Demo ssenarisi (~2 dəqiqə)

1. **Sərnişin (:3000):** xətt seçin → marşrut, canlı avtobuslar və ETA. Dayanacağa klikləyin → gələn
   bütün avtobuslar. "Çox sıxdır" bildirişi göndərin.
2. **Operator (:3001):** cədvəldə "Aşağı" səviyyəli xətti seçin → **"Demo: bu xətti sıxlaşdır"**.
3. ~70 saniyə sonra (11 simulyasiya dəqiqəsi) xəbərdarlıq səs siqnalı ilə görünür və donor xətt tövsiyə olunur.
4. **"N avtobus yönləndir"** → avtobuslar xəttə keçir, sıxlıq azalır.

Linklə birbaşa açmaq: `http://localhost:3000/?line=1&stop=1394`, `http://localhost:3001/?line=1`.

## Problemlərin həlli

| Problem | Həll |
|---|---|
| `python` tapılmır (Windows) | `py -3 -m venv .venv` istifadə edin və ya Python quraşdırarkən "Add to PATH" seçin |
| `RuntimeError: Database is empty` | Backend qovluğunda `python -m app.seed` əmrini işə salın (Addım 2) |
| `Port 3000 is already in use` | Həmin portu tutan proqramı bağlayın və ya başqa port verin: Windows `$env:PORT="3005"; npm run dev:passenger`, macOS/Linux `PORT=3005 npm run dev:passenger` |
| Səhifədə "Server əlçatan deyil" | Backend terminalının işlədiyini yoxlayın (http://localhost:8000/docs) |
| Xəritə boz görünür | İnternet bağlantısını yoxlayın — plitələr OpenStreetMap-dən yüklənir |
| `npm warn install-scripts ... esbuild` | Zərərsizdir, tətbiq işləyir |
| Backend yenidən başladılanda tarixçə itir | Gözlənilir: simulyasiya hər dəfə `SIM_START` saatından yenidən başlayır |

## Məhdudiyyətlər

- Canlı data simulyasiyadır; real tətbiqdə `simulation_service` yerinə avtobusların GPS-i, BakıKart
  validasiyaları (minənlər) və qapı sensorları (düşənlər) qoşulur.
- AYNA-da xətt 144 serverdə xəta verdiyi üçün yüklənmir; 7 xəttin dayanacaq məlumatı yoxdur.
- AYNA marşrut xətlərinin bəziləri tərs istiqamətdə çəkilib və ya dayanacaqlardan keçmir — idxal zamanı
  çevrilir, uyğun gəlməyənlərin yerinə dayanacaqlardan keçən xətt qurulur.
- Operator panelində giriş (login) yoxdur.
- Xəritə plitələri: OpenStreetMap (pulsuz, açarsız; yalnız demo həcmi üçün nəzərdə tutulub).
