# របាយការណ៍សមត្ថភាព និងស្ថាបត្យកម្មប្រព័ន្ធ PBMS SaaS
## PBMS SaaS — Current System Capabilities & Technical Architecture
*កាលបរិច្ឆេទធ្វើបច្ចុប្បន្នភាព៖ ថ្ងៃទី ៣១ ខែតុលា ឆ្នាំ ២០២៦*

---

## ១. ទិដ្ឋភាពទូទៅនៃស្ថាបត្យកម្មប្រព័ន្ធ (High-Level Architecture)

**PBMS SaaS (Printing Business Management System as a Service)** គឺជាប្រព័ន្ធ **Multi-Tenant SaaS + Enterprise Print MIS/ERP** ជំនាន់ថ្មីដែលត្រូវបានរចនាឡើងយ៉ាងពិសេសសម្រាប់ឧស្សាហកម្មបោះពុម្ព និងរោងពុម្ពពាណិជ្ជកម្មនៅកម្ពុជា។

ប្រព័ន្ធដំណើរការលើស្ថាបត្យកម្មទំនើប **Clean Modular Architecture** ដោយបែងចែកជា ៣ Frontends ដាច់ដោយឡែកពីគ្នា ភ្ជាប់ទៅកាន់ Unified Backend API៖

```
                                  ┌────────────────────────────────────────────────────────┐
                                  │                  Browser Client Layer                  │
                                  └──────────────────────────┬─────────────────────────────┘
                                                             │
                  ┌──────────────────────────────────────────┼──────────────────────────────────────────┐
                  ▼                                          ▼                                          ▼
   ┌─────────────────────────────┐            ┌─────────────────────────────┐            ┌─────────────────────────────┐
   │         Frontend A          │            │         Frontend B          │            │         Frontend C          │
   │     Super Admin Portal      │            │  Tenant Printing Workspace  │            │     Public SaaS Website     │
   │         (Port 4201)         │            │         (Port 4202)         │            │         (Port 4200)         │
   │  - Platform Governance      │            │  - Estimation & Quotation   │            │  - Public Pricing Plans     │
   │  - Support Impersonation    │            │  - Production Kanban Board  │            │  - Self-Service Onboarding  │
   │  - Presets Seeder           │            │  - Inventory Ledger         │            │  - KHQR Subscription Pay    │
   │  - Global Broadcasts        │            │  - NBC Bakong KHQR (CAM-001)│            │  - Idempotent Checkout      │
   │  - USB Hardware License     │            │  - Sheet Imposition (PROD)  │            └──────────────┬──────────────┘
   └──────────────┬──────────────┘            │  - GDT VAT Journal (REP-001)│                           │
                  │                           └──────────────┬──────────────┘                           │
                  │                                          │                                          │
                  └──────────────────────────────────────────┼──────────────────────────────────────────┘
                                                             │
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │     Django REST Backend     │
                                              │         (Port 8000)         │
                                              │  - Strict Tenant Isolation  │
                                              │  - Argon2id & Scoped JWT    │
                                              │  - Immutable Audit Events   │
                                              └──────────────┬──────────────┘
                                                             │
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │      PostgreSQL Engine      │
                                              │  - Non-negative Constraints │
                                              │  - Atomic Transactions     │
                                              │  - Read Committed Isolation │
                                              └─────────────────────────────┘
```

---

## ២. ខួរក្បាលគ្រប់គ្រងវេទិកា (SuperAdmin Platform Engine)

SuperAdmin គឺជា **Platform Business Brain** សម្រាប់ Platform Owner គ្រប់គ្រងប្រតិបត្តិការអាជីវកម្មជួលប្រព័ន្ធ ដោយមិនលូកលាន់ទិន្នន័យផ្ទៃក្នុងរបស់ហាងឡើយ៖

### ២.១. មុខងារ Tenant Impersonation («Support Mode»)
- **គោលបំណង:** ដោះស្រាយបញ្ហាជូនអតិថិជនពេលមានការត្អូញត្អែរថា «ចេញវិក្កយបត្រមិនចេញ» ឬ «គណនាលុយខុស» ដោយ SuperAdmin មិនចាំបាច់សុំ Password ពីភ្ញៀវឡើយ។
- **សុវត្ថិភាពខ្ពស់ (Scoped Security):**
  - បង្កើត Token សម្ងាត់មានសុពលភាពត្រឹម **១៥ នាទី (900 វិនាទី)** ដោយកំណត់ Claim `is_impersonation=True` និង `impersonated_by=superadmin_id`។
  - ហាមឃាត់ការបន្លំឆ្លងកាត់ tenant ផ្សេង (Strict Tenant-Scoped Authorization)។
  - កត់ត្រាក្នុង **Immutable Audit Log (`SUPERADMIN_TENANT_IMPERSONATED`)**។
- **UI Feedback:** ផ្នែកខាងលើនៃអេក្រង់ Tenant Workspace នឹងលោត **Sticky Amber Banner** បញ្ជាក់ថា៖ *«របៀបគាំទ្របច្ចេកទេស (Support Mode): កំពុងត្រួតពិនិត្យហាង [ឈ្មោះហាង] ដោយ [SuperAdmin Email]»* រួមជាមួយប៊ូតុង **«🚪 ចាកចេញពី Support Mode»**។

### ២.២. មុខងារ 1-Click Master Printing Catalog Seeder
- **គោលបំណង:** បំបាត់ភាពស្មុគស្មាញក្នុងការបញ្ចូលប្រភេទក្រដាស និងទំហំស្តង់ដារពីសូន្យ នៅពេលហាងថ្មីទើបចុះឈ្មោះ។
- **ទិន្នន័យស្តង់ដារដែលត្រូវបាន Seed ជូន:**
  1. `MAT-AC-300`: **Art Card 300gsm (Couche 2-Side 790x1090mm)** សម្រាប់ធៀបការ, នាមបណ្ណ, ស្លាក Tag
  2. `MAT-AP-150`: **Art Paper 150gsm (Glossy Text 650x900mm)** សម្រាប់ខិត្តប័ណ្ណ, ទស្សនាវដ្តី
  3. `MAT-WF-100`: **Woodfree Paper 100gsm (Book Paper 790x1090mm)** សម្រាប់ក្បាលលិខិត, សៀវភៅ
  4. `MAT-PP-STICKER`: **PP Synthetic Waterproof Sticker Roll** សម្រាប់ស្លាកសញ្ញាផលិតផលមិនជ្រាបទឹក
  5. `MAT-VINYL-380`: **Outdoor Flex Vinyl Banner 380gsm Roll** សម្រាប់ផ្ទាំងប៉ាណូ និងស្លាកយីហោ
  6. **អតិថិជនទូទៅដើម (Default Walk-in Customer):** `012000000 - Walk-in Cash Customer`
- **Onboarding Automation:** ប្រព័ន្ធនឹងដំណើរការ Seed Master Catalog នេះដោយស្វ័យប្រវត្តិកំឡុងពេល SuperAdmin ចុច **Approve Subscription Payment**។

### ២.៣. មុខងារ Global System Broadcast / Announcement
- **គោលបំណង:** ផ្ញើសារជូនដំណឹងភ្លាមៗទៅកាន់គ្រប់ Dashboard របស់ហាងបោះពុម្ពទាំងអស់ (ឧ. ជូនដំណឹងអំពីការ Update មុខងារថ្មី ឬការផ្អាកប្រព័ន្ធដើម្បីថែទាំ)។
- **កម្រិតសារ (Severity Levels):**
  - **`INFO` (ពណ៌ខៀវ):** សេចក្តីជូនដំណឹងទូទៅ និងការណែនាំមុខងារថ្មី
  - **`WARNING` (ពណ៌លឿងទុំ):** ការថែទាំប្រព័ន្ធ (Scheduled Maintenance)
  - **`URGENT` (ពណ៌ក្រហម):** ការជូនដំណឹងអាសន្ន ឬបញ្ហាបន្ទាន់
- **Bilingual:** គាំទ្រទាំងភាសាខ្មែរ និងអង់គ្លេស។ ហាងនីមួយៗអាចចុច Dismiss បិទបានដោយមិនរំខានការងារ។

### ២.៤. បច្ចេកវិទ្យាការពារកម្រិតរឹង SuperAdmin USB Hardware Licensing Dongle
- **កម្រិតការពារ:** SuperAdmin ត្រូវតែដោត USB Flash Drive ដែលមានឯកសារ `license.dat` ដែលមាន **Ed25519/HMAC-SHA256 Digital Signature**។
- **Hardware Binding:** ចងភ្ជាប់ទៅនឹង Volume Serial Number របស់ Flash Drive (`A4B27F91`) ដើម្បីការពារការ Clone ឬចម្លងឯកសារទៅប្រើលើម៉ាស៊ីនផ្សេង។
- **Elevated Token:** នៅពេលផ្ទៀងផ្ទាត់ជោគជ័យ ប្រព័ន្ធផ្តល់ Elevated Token (`X-USB-Elevated-Token`) សម្រាប់បញ្ជា Actions សំខាន់ៗដូចជាការ Reconcile Payment, Tenant Suspension, ឬ Preset Seeding។

### ២.៥. របាយការណ៍អាជីវកម្មវេទិកា (Platform Business Analytics)
- **MRR (Monthly Recurring Revenue):** គណនាចំណូលប្រចាំខែពិតប្រាកដដោយផ្អែកលើ Subscription កំពុងដំណើរការ។
- **Total Orders:** ចំនួន Orders សរុបដែលបានបង្កើតនៅលើប្រព័ន្ធ។
- **Churn Risk Detection:** រាប់ចំនួន Subscription ដែលជិតផុតកំណត់ក្នុងរយៈពេល ៧ ថ្ងៃខាងមុខ។
- **Tenant Status Lifecycle:** Active, Pending Review, Suspended, និង Terminated ដោយរក្សាទិន្នន័យឯកោ server-side។

---

## ៣. ប្រព័ន្ធប្រតិបត្តិការរោងពុម្ព (Tenant Printing MIS / ERP Workspace)

Frontend B (Port 4202) គឺជាប្រព័ន្ធគ្រប់គ្រងការងារបោះពុម្ពពេញលេញសម្រាប់បុគ្គលិករោងពុម្ព៖

### ៣.១. ម៉ាស៊ីនគណនាតម្លៃ និងចេញសម្រង់តម្លៃលម្អិត (Multi-Item Quotation Engine - DOM-001)
- **Multi-Item Line Builder:** អនុញ្ញាតឱ្យបញ្ចូលមុខទំនិញបោះពុម្ពច្រើនក្នុង Quote តែមួយ (ឧ. នាមបណ្ណ ១០០០ សន្លឹក + ក្បាលសំបុត្រ ៥០០ សន្លឹក + Rollup Banner ២ ផ្ទាំង)។
- **Deterministic Pricing Breakdown:**
  $$\text{Subtotal} = \sum (\text{Qty} \times \text{Unit Price} + \text{Setup Fee} + \text{Finishing Fee})$$
  $$\text{Tax Amount} = (\text{Subtotal} - \text{Discount}) \times \text{Tax Rate \%}$$
  $$\text{Total KHR} = \text{Total USD} \times \text{Exchange Rate (KHR)}$$
- **1-Click Conversion Pipeline:** បម្លែងពី Quotation ទៅជា **Confirmed Sales Order** ដោយស្វ័យប្រវត្តិនឹងបង្កើត **Production Job** និង **Tax Invoice** ក្នុង transaction តែមួយ។

### ៣.២. ក្ដារខៀនផលិតកម្មឆ្លាតវៃ (Smart UI Drag-and-Drop Production Kanban Board)
- **ដំណាក់កាលផលិតកម្មទាំង ៦ (6 Production Stages):**
  1. `PENDING` (រង់ចាំការត្រួតពិនិត្យ)
  2. `PRE_PRESS` (ត្រួតពិនិត្យ Artwork & ឌីហ្សាញ)
  3. `PRINTING` (កំពុងរត់ម៉ាស៊ីនព្រីន Offset / Digital)
  4. `FINISHING` (កាត់, បត់, កាវ, ស្រោប UV/Matte)
  5. `QC` (ត្រួតពិនិត្យគុណភាពផ្ទៀងផ្ទាត់គំរូ)
  6. `COMPLETED` (រួចរាល់រង់ចាំប្រគល់ជូនភ្ញៀវ)
- **Role-Gated Stage Transitions:**
  - **Graphic Designer:** អាចទាញ Order ពី `PENDING` $\rightarrow$ `PRE_PRESS`
  - **Production Staff:** អាចទាញឆ្លងកាត់ដំណាក់កាលព្រីន, កែច្នៃ, និង QC
  - **Manager / Owner:** មានសិទ្ធិពេញលេញលើគ្រប់ដំណាក់កាលទាំងអស់

### ៣.៣. បញ្ជីស្តុកទំនិញសុចរិតភាព (Immutable Inventory Ledger & Check Constraints)
- **គោលការណ៍ Double-Entry Ledger:** រាល់ការប្រែប្រួលចំនួនស្តុកក្រដាស ទឹកថ្នាំ ឬ Sticker ត្រូវតែកត់ត្រាជា Ledger Transaction (`operations_inventorytransaction`)។
- **ប្រតិបត្តិការ ៥ ប្រភេទ:** `STOCK_IN`, `CONSUMPTION`, `WASTE`, `OFFCUT_RETURN`, `ADJUSTMENT`។
- **ការការពារកម្រិត Database (Invariant):** អនុវត្ត PostgreSQL Check Constraint `chk_material_stock_non_negative` ធានាដាច់ខាតថាស្តុកមិនអាចអវិជ្ជមាន (`current_stock >= 0`)។

### ៣.៤. មុខងារបង់ប្រាក់ស្វ័យប្រវត្តិតាមធនាគារជាតិនៃកម្ពុជា (NBC Bakong KHQR - CAM-001)
- **EMVCo Compliant KHQR:** បង្កើតកូដ QR តាមស្តង់ដារបស់ធនាគារជាតិនៃកម្ពុជា គាំទ្រទាំងប្រាក់រៀល (KHR - `4100`) និងប្រាក់ដុល្លារ (USD - `840`)។
- **Bakong Deep-Link Integration:** បង្ហាញ QR Code លើ Modal ផ្ទាល់សម្រាប់ភ្ញៀវស្កេនបង់តាម Mobile Banking (ABA, Acleda, Canadia, Wing, etc.)។
- **Copy KHQR String:** ប៊ូតុង Copy Payload សម្រាប់ផ្ញើតាម Telegram ឬ Messenger។
- **Dynamic KHQR Payload Construction:** រួមបញ្ចូល CRC16 checksum, Merchant Category Code (`5943`), និង Merchant Name ស្របច្បាប់។

### ៣.៥. ឧបករណ៍រៀបពុម្ពកាត់ក្រដាសពាណិជ្ជកម្ម (Commercial Sheet Imposition & Cut Optimizer - PROD-001)
- **2D Rectangular Nesting Optimizer:** គណនាការដាក់ប្លង់កាត់ទំហំតូច (A4, A5, Card) លើសន្លឹកក្រដាសធំ (790x1090, 650x900, 700x1000, 330x483)។
- **ក្បួនដោះស្រាយវិស្វកម្មបោះពុម្ព:**
  - ប្រៀបធៀបរវាង Unrotated, 90° Rotated, និង Combination Layouts ដើម្បីស្វែងរកចំនួនសន្លឹកអតិបរមា (Max Yield)។
  - កំណត់គម្លាត Gripper Margin (10mm) សម្រាប់ម៉ាស៊ីន Offset ចាប់សន្លឹក។
  - កំណត់គម្លាត Bleed (2mm) និង Cutting Margin (5mm)។
  - គណនាភាគរយ Waste % និង Spoilage Buffer (Makeready sheets)។
- **Live Scalable Vector Graphics (SVG):** បង្ហាញគំនូសព្រាងប្លង់កាត់ជាក់ស្តែង និងពណ៌នាទីតាំងសន្លឹកកាត់នីមួយៗនៅលើអេក្រង់។

### ៣.៦. របាយការណ៍សៀវភៅលក់ជាប់អាករជូនពន្ធដារ (GDT Official VAT Sales Journal - REP-001)
- **ទម្រង់ស្តង់ដារអគ្គនាយកដ្ឋានពន្ធដារ (GDT Format):**
  - ចាត់ថ្នាក់វិក្កយបត្រតាមខែ និងឆ្នាំ
  - បំបែកតម្លៃជាប់ពន្ធ (Taxable Amount), អាករលើតម្លៃបន្ថែម (VAT 10%), និងតម្លៃសរុប (Total Sales)
  - បំប្លែងទាំងរូបិយប័ណ្ណ USD និង KHR តាមអត្រាប្តូរប្រាក់ផ្លូវការ
- **Export Excel / CSV Compatibility:** ទាញយកឯកសារជា `.csv` ជាមួយ **UTF-8 BOM Header** ការពារកុំឱ្យខូចពុម្ពអក្សរខ្មែរពេលបើកក្នុង Microsoft Excel។

### ៣.៧. ផ្ទាំងគ្រប់គ្រងបែបម៉ូឌុល (Customizable Modular Dashboard Widgets)
- អ្នកប្រើប្រាស់អាចទាញផ្លាស់ប្តូរទីតាំង (Drag-and-Drop Reorder) នៃកាតសង្ខេប Metric លើ Dashboard តាមចំណូលចិត្ត៖
  - ការបញ្ជាទិញសរុប (Sales Orders)
  - ការងារផលិតកម្មកំពុងដំណើរការ (Active Jobs)
  - ចំណូលប្រមូលបានសរុប (Collected Payments)
  - បំណុលអតិថិជននៅជំពាក់ (Outstanding Balance)

### ៣.៨. ការបែងចែកសិទ្ធិបុគ្គលិកតាមតួនាទី (Role-Based Access Control - RBAC)
- ប្រព័ន្ធបែងចែកតួនាទីចំនួន ៧ យ៉ាងតឹងរ៉ឹង៖
  1. `TENANT_OWNER`: សិទ្ធិពេញលេញលើការគ្រប់គ្រង, ការកំណត់ពន្ធ/អត្រាប្តូរប្រាក់, បុគ្គលិក, ហិរញ្ញវត្ថុ
  2. `TENANT_MANAGER`: សិទ្ធិគ្រប់គ្រងសម្រង់តម្លៃ, ការបញ្ជាទិញ, ផលិតកម្ម, ស្តុក, និងវិក្កយបត្រ
  3. `SALES_STAFF`: សិទ្ធិចេញ Quote, បង្កើត Order, ពិនិត្យវិក្កយបត្រ និងទូទាត់ប្រាក់
  4. `DESIGNER`: សិទ្ធិពិនិត្យការងារ Pre-Press និងផ្ទុកឡើងឯកសារ Artwork
  5. `PRODUCTION_STAFF`: សិទ្ធិគ្រប់គ្រងដំណើរការព្រីន និងកាត់កែច្នៃ
  6. `INVENTORY_STAFF`: សិទ្ធិបញ្ចូលស្តុក និងកត់ត្រាការខូចខាតវត្ថុធាតុដើម
  7. `FINANCE_STAFF`: សិទ្ធិគ្រប់គ្រងវិក្កយបត្រ, របាយការណ៍ពន្ធ VAT, និងការកត់ត្រាប្រាក់ចំណូល

---

## ៤. គេហទំព័រសាធារណៈ និងការជាវសេវា (Frontend C - Public Site)

Frontend C (Port 4200) គឺជាទំព័រមុខសម្រាប់បង្ហាញផលិតផល និងអនុញ្ញាតឱ្យអតិថិជនថ្មីចុះឈ្មោះដោយខ្លួនឯង (Self-Service Registration)៖
- **Subscription Tiers:**
  - **Starter Print Shop ($29/ខែ ឬ $290/ឆ្នាំ):** សម្រាប់រោងពុម្ពខ្នាតតូច បុគ្គលិក ៥ នាក់
  - **Growth Printing Press ($59/ខែ ឬ $590/ឆ្នាំ):** ប្រព័ន្ធពេញលេញ ស្តុក និង Kanban បុគ្គលិក ២០ នាក់
  - **Enterprise Industrial Press ($119/ខែ ឬ $1190/ឆ្នាំ):** សម្រាប់រោងពុម្ពឧស្សាហកម្មខ្នាតធំ បុគ្គលិក ១០០ នាក់
- **Idempotency Key Protection:** ការពារការចុះឈ្មោះ ឬកាត់លុយស្ទួនពេលបណ្តាញអ៊ីនធឺណិតមានការរអាក់រអួល។

---

## ៥. កាតាឡុក API Endpoints សរុប (API Endpoints Catalog)

បច្ចុប្បន្ន ប្រព័ន្ធមាន **៣៨ Core REST API Endpoints (`/api/v1/`)** ដែលត្រូវបានការពារ និងផ្ទៀងផ្ទាត់សុវត្ថិភាពយ៉ាងហ្មត់ចត់៖

| ល.រ | Method | API Endpoint Path | ការពិពណ៌នា និងសិទ្ធិអនុញ្ញាត |
| :---: | :---: | :--- | :--- |
| **១** | `POST` | `/api/v1/auth/login/` | ចូលប្រើប្រាស់ប្រព័ន្ធ (Argon2id + JWT + Session Tracking) |
| **២** | `POST` | `/api/v1/auth/refresh/` | បន្តសុពលភាព Token (Atomic Family Rotation & Reuse Detection) |
| **៣** | `POST` | `/api/v1/auth/logout/` | ចាកចេញពី Session បច្ចុប្បន្ន (Session Revocation) |
| **៤** | `POST` | `/api/v1/auth/logout-all/` | ចាកចេញពីគ្រប់ឧបករណ៍ទាំងអស់ (Revoke All Sessions) |
| **៥** | `GET` | `/api/v1/auth/me/` | មើលព័ត៌មានគណនី និងសិទ្ធិផ្ទាល់ខ្លួន |
| **៦** | `GET` | `/api/v1/health/` | ពិនិត្យសុខភាពប្រព័ន្ធ និង Database Connectivity |
| **៧** | `GET` | `/api/v1/announcements/active/` | ទាញយកសារជូនដំណឹងសកម្មទូទាំងប្រព័ន្ធ (Public/Tenant) |
| **៨** | `GET` | `/api/v1/super-admin/announcements/` | បញ្ជីសារជូនដំណឹងទាំងអស់ (SuperAdmin Only) |
| **៩** | `POST` | `/api/v1/super-admin/announcements/` | បង្កើត និងផ្សាយដំណឹងថ្មី (SuperAdmin Only) |
| **១០** | `PATCH`| `/api/v1/super-admin/announcements/<id>/` | បើក/បិទ ឬកែសម្រួលសារជូនដំណឹង (SuperAdmin Only) |
| **១១** | `DELETE`| `/api/v1/super-admin/announcements/<id>/`| លុបសារជូនដំណឹងចេញពីប្រព័ន្ធ (SuperAdmin Only) |
| **១២** | `GET` | `/api/v1/public/plans/` | មើលកញ្ចប់សេវាកម្ម Subscription សាធារណៈ |
| **១៣** | `POST` | `/api/v1/public/register-tenant/` | ចុះឈ្មោះហាងថ្មី និងបង្កើតគណនីដំបូង (Idempotent) |
| **១៤** | `GET` | `/api/v1/super-admin/overview/` | របាយការណ៍អាជីវកម្មវេទិកា (MRR, Total Orders, Churn Risk) |
| **១៥** | `GET` | `/api/v1/super-admin/tenants/` | បញ្ជីហាងបោះពុម្ពទាំងអស់ក្នុងប្រព័ន្ធ |
| **១៦** | `POST` | `/api/v1/super-admin/payments/<id>/reconcile/` | អនុម័តការបង់ប្រាក់ជួលប្រព័ន្ធ + Auto Seed Presets |
| **១៧** | `POST` | `/api/v1/super-admin/tenants/<id>/status/` | ផ្អាកហាងបណ្ដោះអាសន្ន (Suspend) ឬបើកដំណើរការវិញ (Activate) |
| **១៨** | `POST` | `/api/v1/super-admin/tenants/<id>/impersonate/` | ចូលពិនិត្យក្នុងនាមហាង (Support Mode Scoped Token) |
| **១៩** | `POST` | `/api/v1/super-admin/tenants/<id>/seed-presets/` | បញ្ចូល Master Catalog Presets សម្រាប់ហាង (1-Click Seed) |
| **២០** | `POST` | `/api/v1/super-admin/license/verify/` | ផ្ទៀងផ្ទាត់ SuperAdmin USB Hardware Key |
| **២១** | `POST` | `/api/v1/super-admin/license/revoke/` | លុបចោលកូនសោរ USB ដែលបាត់ ឬខូច |
| **២២** | `GET` | `/api/v1/tenant/settings/` | មើលការកំណត់របស់ហាង (អត្រាប្តូរប្រាក់ KHR & អត្រាពន្ធ) |
| **២៣** | `PATCH`| `/api/v1/tenant/settings/` | កែប្រែការកំណត់ហាង (Owner Only + Audit Log) |
| **២៤** | `GET` | `/api/v1/tenant/context/` | ផ្ទៀងផ្ទាត់សុពលភាព Subscription & សិទ្ធិហាង |
| **២៥** | `GET` | `/api/v1/tenant/dashboard/` | ទាញទិន្នន័យ Modular Metrics សង្ខេបលើ Dashboard |
| **២៦** | `GET, POST` | `/api/v1/tenant/customers/` | មើល និងចុះឈ្មោះអតិថិជនថ្មី |
| **២៧** | `GET, POST` | `/api/v1/tenant/quotations/` | មើល និងបង្កើតសម្រង់តម្លៃ Multi-Item (DOM-001) |
| **២៨** | `POST` | `/api/v1/tenant/quotations/<id>/convert/` | បម្លែងពី Quote ទៅជា Confirmed Sales Order + Job |
| **២៩** | `GET, POST` | `/api/v1/tenant/orders/` | មើល និងគ្រប់គ្រងការបញ្ជាទិញផលិតកម្ម |
| **៣០** | `PATCH`| `/api/v1/tenant/production-jobs/<id>/stage/` | ប្តូរដំណាក់កាលផលិតកម្មលើ Kanban Board |
| **៣១** | `GET, POST` | `/api/v1/tenant/materials/` | មើល និងគ្រប់គ្រងបញ្ជីសម្ភារៈ និងក្រដាស |
| **៣២** | `GET, POST` | `/api/v1/tenant/inventory-movements/` | កត់ត្រាចលនាស្តុកចូល-ចេញក្នុង Immutable Ledger |
| **៣៣** | `GET, POST` | `/api/v1/tenant/invoices/` | មើល និងចេញវិក្កយបត្រជូនអតិថិជន |
| **៣៤** | `GET` | `/api/v1/tenant/invoices/<id>/khqr/` | បង្កើតកូដ NBC Bakong KHQR តាមវិក្កយបត្រ (USD/KHR) |
| **៣៥** | `POST` | `/api/v1/tenant/invoices/<id>/payments/` | កត់ត្រាការបង់ប្រាក់របស់អតិថិជន (Payment Allocation) |
| **៣៦** | `GET, POST, DEL` | `/api/v1/tenant/memberships/` | គ្រប់គ្រងគណនីបុគ្គលិក និងតួនាទី RBAC ក្នុងហាង |
| **៣៧** | `POST` | `/api/v1/tenant/tools/imposition/` | គណនាប្លង់កាត់ក្រដាស និងបង្កើតគំនូរ SVG (PROD-001) |
| **៣៨** | `GET` | `/api/v1/tenant/reports/vat-sales-journal/` | របាយការណ៍សៀវភៅលក់ជាប់អាករពន្ធដារ (JSON & CSV) |

---

## ៦. សូចនាករផ្ទៀងផ្ទាត់គុណភាពកម្រិតផលិតកម្ម (Production Verification Metrics)

រាល់មុខងារទាំងអស់ត្រូវបានសាកល្បង និងផ្ទៀងផ្ទាត់ដោយជោគជ័យ ១០០%៖

- **Backend Concurrency & Integrity Tests:**
  - **73 / 73 Tests PASSED** លើ PostgreSQL Engine ពិតប្រាកដ
  - រួមបញ្ចូល Concurrency Tests, Non-Negative Stock Checks, Scoped Token Verification, និង USB Licensing
- **Frontend Reactive & State Recovery Tests:**
  - **44 / 44 Tests PASSED**
  - រួមបញ្ចូល 401 Session Recovery Deduplication, Smart Kanban Role Transitions, និង Sheet Imposition Engine
- **Production Builds Compilation:**
  - `public-site` (Frontend C): **SUCCESS**
  - `super-admin` (Frontend A): **SUCCESS**
  - `tenant-workspace` (Frontend B): **SUCCESS**
- **Git Version Control:**
  - Clean History, No Secrets, Conventional Commits
  - Branch: `feat/task-04-production-settings-hardening-11635122478871391506`
  - Commit ID: `74ab6bc` (Pushed to Remote Origin)
