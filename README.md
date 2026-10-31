# Smart Transit & Crowdsourcing Engine — Bakı

Bakı avtobus şəbəkəsi üçün funksional prototip: sərnişinlər canlı avtobus mövqeyini və gəliş vaxtını (ETA) görür,
operatorlar isə xətlər üzrə sıxlığı izləyir və sıxlıq 10 dəqiqə "Yüksək" qalanda avtomatik
**"Əlavə avtobus ehtiyatı ayrılmalıdır"** bildirişi alır.

- **Real şəbəkə:** 208 xətt, 3 450 dayanacaq, yol həndəsəsi — [map.ayna.gov.az](https://map.ayna.gov.az/) ictimai API-sindən.
- **Saxta canlı data:** GPS, sərnişin sayğacı və sərnişin bildirişləri simulyatorla yaradılır (real feed yoxdur).

## Arxitektura

```
frontend (React + Leaflet/OpenStreetMap)
   │  REST /api/*      WebSocket /ws/live
backend (FastAPI)
   ├── controller/   HTTP + WebSocket, Pydantic sxemləri          ← yalnız giriş/çıxış
   ├── business/     servislər: ETA, sərnişin, operator, analitika,
   │                 simulyator, data idxalı, mühərrik (engine)    ← iş məntiqi
   ├── domain/       modellər, enum-lar, qaydalar (rules.py), geo   ← təmiz funksiyalar, I/O yoxdur
   └── repository/   SQLite sorğuları, sxem (schema.sql)            ← verilənlər bazası
```

Qatlar yalnız aşağıya müraciət edir: `controller → business → domain/repository`.
Analitika və ETA yalnız repository-dən oxuyur, ona görə simulyatoru real GPS/APC feed ilə əvəz etmək
digər kodu dəyişmir.

### Verilənlər bazası (`backend/database/transport.db`, SQLite)

| Cədvəl | Məzmun |
|---|---|
| `lines` | Xətlər (nömrə, daşıyıcı, son dayanacaqlar, uzunluq, tarif) |
| `stops` | Dayanacaqlar (ad, ünvan, GPS) — paylaşılan dayanacaq bir dəfə saxlanır |
| `line_stops` | Xəttin istiqamət üzrə dayanacaq ardıcıllığı və marşrut üzrə məsafəsi |
| `route_shapes` | Xəttin yol həndəsəsi (hər istiqamət üçün) |
| `buses` | Avtobuslar: `line_id, bus_id, bus_plate, passenger_count, passenger_percentage, passenger_limit, forwarding_stop_id, live_longitude, live_latitude` + istiqamət, status, sürət |
| `bus_telemetry` | GPS və sərnişin sayı tarixçəsi (dəqiqəlik) |
| `crowd_reports` | Sərnişin bildirişləri (aşağı / orta / yüksək) |
| `line_density` | Xətt üzrə dəqiqəlik sıxlıq ölçmələri |
| `alerts` | Operator xəbərdarlıqları |

## İşə salma

### 1. Backend (Python 3.12+)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m app.seed            # bazanı backend/sources/bus_lines.json-dan qurur
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

- API sənədləri: http://127.0.0.1:8000/docs
- `python -m app.seed --refresh` — datanı AYNA-dan yenidən yükləyir.

Parametrlər (mühit dəyişənləri):

| Dəyişən | Default | Məna |
|---|---|---|
| `SIM_SPEED` | `10` | 1 real saniyə = 10 simulyasiya saniyəsi |
| `SIM_START` | `08:00` | Simulyasiyanın başlanğıc saatı (pik saat 07:30–09:30, 17:30–19:30) |
| `TICK_SECONDS` | `1` | Simulyasiya addımı (real saniyə) |
| `SIM_SEED` | `42` | Təsadüfi ədədlər üçün toxum (təkrarlana bilən nəticə) |

### 2. Frontend (Node.js 20+)

```powershell
cd frontend
npm install
npm run dev        # http://localhost:3000  (/api və /ws backend-ə proxy olunur)
```

Bu kompüterdə Node.js portativ şəkildə `..\tools\node` qovluğundadır:
`$env:Path = "C:\Users\1507Student\Desktop\project\tools\node;$env:Path"`.

## Necə işləyir

### Sıxlıq balı (0–100)

```
doluluq      = xəttdə xidmətdə olan avtobusların orta doluluq faizi
bildiriş balı = son 10 dəqiqənin sərnişin bildirişlərinin ortası (aşağı=25, orta=65, yüksək=95)
çəki          = 0.3 × min(1, bildiriş sayı / 5)
bal           = (1 − çəki) × doluluq + çəki × bildiriş balı
```

Səviyyə: `< 50` Aşağı, `50–85` Orta, `> 85` Yüksək. Bir-iki (bəlkə də səhv) bildiriş sayğac məlumatını
üstələyə bilmir; bildiriş çoxaldıqca onların çəkisi 30%-ə qədər artır. Son dayanacaqda fasilədə olan boş
avtobuslar ortalamaya daxil edilmir.

### Anomaliya xəbərdarlığı

- Hər simulyasiya dəqiqəsində bütün xətlər üçün bal hesablanır və `line_density`-ə yazılır.
- Xətt son **10 dəqiqənin bütün ölçmələrində "Yüksək"** olubsa və açıq bildirişi yoxdursa →
  "Əlavə avtobus ehtiyatı ayrılmalıdır" bildirişi yaranır.
- Tövsiyə olunan avtobus sayı balı 85-ə endirmək üçün lazım olan saya görə hesablanır (1–5).
- **Donor xətt:** 8 km radiusda ən boş "Aşağı" səviyyəli xətt (yoxdursa, ən yaxını).
- Operator "N avtobus yönləndir" düyməsi ilə avtobusları donor xətdən köçürür, ya da bildirişi bağlayır.
- Sıxlıq 5 dəqiqə ardıcıl "Yüksək"dən aşağı olsa, bildiriş avtomatik bağlanır.

### ETA

Avtobusun marşrut üzrə mövqeyindən dayanacağa qədər yol məsafəsi ÷ avtobusun son 5 dəqiqədəki orta hərəkət
sürəti + aradakı hər dayanacaq üçün 30 saniyə.

### Simulyator

- Avtobuslar real AYNA marşrut xətləri üzrə hərəkət edir; pik saatlarda sürət azalır.
- Sərnişinlər dayanacaqlara sabit tempdə gəlir və avtobus gələnə qədər gözləyir (uzun gözləyən bir hissə
  imtina edir). Buna görə xəttə avtobus əlavə etmək hər avtobusa düşən yükü real olaraq azaldır.
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
| WS | `/ws/live?line_id=&operator=true` | Hər 2 saniyədən bir canlı yeniləmə |

## Demo ssenarisi (~2 dəqiqə, `SIM_SPEED=10`)

1. **Sərnişin:** xətt seçin → marşrut, canlı avtobuslar və növbəti dayanacağa ETA. Dayanacağa klikləyin →
   gələn bütün avtobuslar və ETA. "Çox sıxdır" bildirişi göndərin.
2. **Operator paneli:** cədvəldə "Aşağı" səviyyəli xətti seçin → **"Demo: bu xətti sıxlaşdır"**.
3. ~70 saniyə sonra (11 simulyasiya dəqiqəsi) xəbərdarlıq səs siqnalı ilə görünür və donor xətt tövsiyə olunur.
4. **"N avtobus yönləndir"** → avtobuslar xəritədə xəttə keçir, sıxlıq azalır.

## Məhdudiyyətlər

- Canlı data simulyasiyadır; real tətbiqdə `simulation_service` yerinə GPS/APC inteqrasiyası qoşulur.
- AYNA-da xətt 144 serverdə xəta verdiyi üçün yüklənmir; 7 xəttin dayanacaq məlumatı yoxdur.
- AYNA marşrut xətlərinin bəziləri tərs istiqamətdə çəkilib və ya dayanacaqlardan keçmir — idxal zamanı
  çevrilir, uyğun gəlməyənlərin yerinə dayanacaqlardan keçən xətt qurulur.
- Xəritə plitələri: OpenStreetMap (pulsuz, açarsız; yalnız demo həcmi üçün nəzərdə tutulub).
