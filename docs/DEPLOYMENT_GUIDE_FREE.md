# ការណែនាំអំពីការដាក់ឲ្យដំណើរការប្រព័ន្ធដោយចំណាយ $0 ឬក្រោម $10/ខែ (Zero-Cost & Low-Cost Deployment Guide)

ឯកសារនេះរៀបចំឡើងជាពិសេសសម្រាប់ **ការការពារសារណាបញ្ចប់ឆ្នាំសិក្សា (Final University Thesis Presentation / Capstone Defense)** និងការដាក់ឲ្យដំណើរការជាសាធារណៈដោយសន្សំសំចៃបំផុត។

---

## យុទ្ធសាស្ត្រជ្រើសរើស (Deployment Strategy Matrix)

| ជម្រើស (Option) | ថ្លៃដើម (Cost) | សមស្របសម្រាប់ (Best For) | ភាពទុកចិត្ត (Reliability) |
| :--- | :--- | :--- | :--- |
| **ជម្រើស A: 100% Free Cloud ($0/mo)** | **$0.00 / ខែ** | ដាក់បង្ហាញលើ Internet ឲ្យគ្រូមើលពីចម្ងាយ | ខ្ពស់ (បិទ/បើកតាម Sleep policy) |
| **ជម្រើស B: Google Cloud ($10 Credit)** | **<$5 - $10 / ខែ** | ប្រើ Google Cloud Run + Firebase Hosting | ខ្ពស់បំផុត (Enterprise-grade) |
| **ជម្រើស C: Local Laptop Offline Demo** | **$0.00** | **ការពារពេល Wi-Fi សាលាដាច់ ឬខ្សោយ** | **១០០% ធានាថាមិនរអាក់រអួល** |

---

## ជម្រើស A: ការដាក់ឲ្យដំណើរការ Cloud ១០០% ឥតគិតថ្លៃ ($0/Month Stack)

### ១. ផ្នែកទិន្នន័យ (Database): Neon.tech (Serverless PostgreSQL)
- **តម្លៃ:** ឥតគិតថ្លៃ ($0/mo) សម្រាប់ទំហំ 0.5 GB Storage និង Compute គ្រប់គ្រាន់។
- **គុណសម្បត្តិ:** ជា PostgreSQL 16 ពិតប្រាកដ (គាំទ្រ Check Constraints, Non-negative stock ledger, Foreign keys)។
- **របៀបដំឡើង:**
  1. ចុះឈ្មោះគណនីឥតគិតថ្លៃនៅ [Neon.tech](https://neon.tech)
  2. បង្កើត Database ឈ្មោះ `pbms_prod`
  3. ចម្លងយក Connection String (ឧ. `postgres://alex:secret@ep-cool-fog-123.ap-southeast-1.aws.neon.tech/pbms_prod?sslmode=require`)

### ២. ផ្នែកម៉ាស៊ីនមេ Backend: Render.com ឬ Railway
- **តម្លៃ:** Render Web Service Free Tier ($0/mo)
- **ការកំណត់ Environment Variables លើ Render:**
  ```env
  DJANGO_SETTINGS_MODULE=config.settings
  DJANGO_SECRET_KEY=generate-a-strong-random-secret-key-for-prod
  DJANGO_DEBUG=False
  DJANGO_ALLOWED_HOSTS=.onrender.com,localhost,127.0.0.1
  DATABASE_URL=postgres://alex:secret@ep-cool-fog-123.ap-southeast-1.aws.neon.tech/pbms_prod?sslmode=require
  JWT_SIGNING_KEY=generate-jwt-secret-key
  CORS_ALLOWED_ORIGINS=https://your-public-site.vercel.app,https://your-tenant.vercel.app,https://your-admin.vercel.app
  ```
- **Build & Start Commands:**
  - Build Command: `pip install -r backend/requirements.txt && python backend/manage.py migrate`
  - Start Command: `gunicorn --chdir backend config.wsgi:application --bind 0.0.0.0:$PORT`

### ៣. ផ្នែកផ្ទៃកម្មវិធី Frontend (A, B, C): Vercel ឬ Cloudflare Pages
- **តម្លៃ:** $0/mo (Free Tier ផ្តល់ Bandwidth 100GB/ខែ និង Custom Subdomain ដោយឥតគិតថ្លៃ)
- **គម្រោងដែលត្រូវ Deploy:**
  - `pbms-public`: Landing Page & Registration (`npm run build:public`)
  - `pbms-tenant`: Workspace សម្រាប់ហាងបោះពុម្ព (`npm run build:tenant`)
  - `pbms-admin`: SuperAdmin Platform Control (`npm run build:admin`)

---

## ជម្រើស B: Google Cloud Platform (ប្រើប្រាស់ជាមួយ Credit $10/ខែ)

ប្រសិនបើអ្នកមាន Google Cloud Credit $10/ខែ ពី Google AI Pro អ្នកអាចដំណើរការ Serverless Stack យ៉ាងងាយស្រួល៖

### ១. Google Cloud Run (Backend API)
- Cloud Run គិតលុយតែនៅពេលមាន Request ចូលប៉ុណ្ណោះ (Pay-per-use)។
- Free Tier ប្រចាំខែរបស់ Google Cloud រួមមាន **2 លាន Requests ឥតគិតថ្លៃ** និង vCPU-hours ច្រើនគួរសម។
- ដូច្នេះ ការ Demo ជូនគណៈកម្មការ និងគ្រូ គឺស្ទើរតែ **$0.00** មិនអស់សូម្បី $1 នៃកញ្ចប់ $10 របស់អ្នក។

### ២. Firebase Hosting (Frontends)
- ឥតគិតថ្លៃ 100% សម្រាប់ផ្ទុក Static Single Page Apps (Angular SSR/SPA) រួមជាមួយ SSL Certificate ស្វ័យប្រវត្តិ។

---

## ជម្រើស C: វិធានការសុវត្ថិភាពខ្ពស់បំផុត — Offline Laptop Demo (សង្គ្រោះពេលការពារសារណា)

> [!CAUTION]
> **ការព្រមានសំខាន់សម្រាប់ការការពារសារណា (Defense Presentation):**
> បញ្ហាទូទៅបំផុតក្នុងបន្ទប់ការពារសារណានៅសាកលវិទ្យាល័យ គឺ **Wi-Fi សាលាដាច់ ឬស្លាប់ (Slow Connection)**។ ប្រសិនបើពឹងផ្អែកតែលើ Cloud ១០០% នោះការ Demo អាចនឹងគាំង។ ដូច្នេះ អ្នកត្រូវតែមានគម្រោង Backup លើ Laptop ផ្ទាល់ខ្លួនជាដាច់ខាត!

### ដំណើរការងាយៗដោយប្រើ Docker Compose (មិនបាច់មានអ៊ីនធឺណិត)៖

១. **បើកប្រព័ន្ធទាំងមូលដោយបញ្ជាតែមួយ៖**
```bash
docker compose up -d
```
Docker នឹងដំណើរការ៖
- PostgreSQL Database (`localhost:5432`)
- Django REST Backend API (`localhost:8000`) រួមជាមួយការ Migration និងការ Seed Data ស្វ័យប្រវត្តិ។

២. **ដំណើរការ Frontend លើ Terminal ដាច់ដោយឡែក (ក្នុង Folder `frontend`)៖**
```bash
# 1. ដំណើរការ Public Site (Frontend C)
npm run start:public      # បើក http://localhost:4200

# 2. ដំណើរការ Super Admin (Frontend A)
npm run start:admin       # បើក http://localhost:4201

# 3. ដំណើរការ Tenant Workspace (Frontend B)
npm run start:tenant      # បើក http://localhost:4202
```

---

## សេណារីយ៉ូសម្រាប់ការធ្វើ Demo មុខគ្រូ (10-Minute Presentation Flow)

1. **នាទីទី 1-2: បង្ហាញ Public Site & Solo Plan ($10/ខែ)**
   - បើក `http://localhost:4200`
   - បង្ហាញជម្រើសកញ្ចប់តម្លៃទាំង ៤ (Solo/Family, Starter, Growth, Enterprise)។
   - ពន្យល់គ្រូអំពី **Algorithm ទប់ស្កាត់ការបន្លំប្រើគណនី (2 Concurrent Active Sessions Guard)** សម្រាប់កញ្ចប់ Family/Solo។
   - ចុះឈ្មោះហាងថ្មី (ឧ. `vattanak-print`)។

2. **នាទីទី 3-4: SuperAdmin Verification & Presets Seeder**
   - បើក `http://localhost:4201`
   - បង្ហាញផ្ទាំង SuperAdmin ផ្ទៀងផ្ទាត់ការបង់ប្រាក់ Reconcile KHQR។
   - ចុចជ្រើសរើស **Seed Presets** (ជ្រើសរើសរវាង `🌱 Digital Quick-Print Pack` សម្រាប់ហាងតូច ឬ `🏭 Commercial Offset Pack` សម្រាប់រោងពុម្ពធំ)។

3. **នាទីទី 5-7: Tenant Workspace & Dual Tax Regime**
   - បើក `http://localhost:4202` ចូលជាម្ចាស់ហាង។
   - ចូលទៅកាន់ **Settings (ការកំណត់រោងពុម្ព)**៖
     - បង្ហាញការប្តូររវាង **«អាជីវកម្មគ្រួសារ 0% VAT»** និង **«រោងពុម្ពចុះបញ្ជីពន្ធដារ VAT 10%»**។
     - បង្ហាញថានៅពេលរើសរបបគ្រួសារ ប្រព័ន្ធបិទ VAT ចោលភ្លាមៗដោយសុវត្ថិភាព។

4. **នាទីទី 8-10: Multi-Item Quotation & Production Kanban Board**
   - បង្ហាញការបង្កើត Quotation មានច្រើន Line Items (នាមបណ្ណ + ក្បាលសំបុត្រ + Rollup Banner)។
   - ធ្វើការ Drag-and-Drop ប្តូរ Stage លើ **Production Kanban Board** (`PENDING` -> `PRINTING` -> `QC` -> `COMPLETED`)។
   - បើកមើល **Tax Invoice / Cash Receipt** ស្របតាមច្បាប់ពន្ធដារកម្ពុជា (GDT) និង NBC Bakong KHQR។
