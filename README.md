# 🕒 Working-Hours-E  
### 工作時數 E 指通 — SaaS 1.0

**Working-Hours-E** is a lightweight SaaS platform designed for professional service workers to record working hours, securely share records with necessary partners, and maintain privacy and data integrity.

The current version is optimized for **Orientation & Mobility (O&M)** and **ADL (daily living skills)** professionals, enabling transparent collaboration between teachers, agencies, and service coordinators.

---

## 🌟 Core Features

### 👩‍🏫 Teacher Dashboard
- Create and manage service cases
- Record daily working sessions
- Track granted, used, and remaining hours
- Export annual records as CSV for audit and reporting

### 🔐 Secure Verification
- Each case generates a **one-time query code**
- Agencies can verify records without accessing personal login data
- Query codes are encrypted and hashed for safety

### 🏢 Partner Lookup Interface
- Agencies can check:
  - Used hours
  - Remaining hours
  - Detailed session history
- Only authorized partners with the correct query code can view records

### 🧹 Automatic Annual Cleanup
- Old data is automatically removed after each fiscal year
- Keeps the database lightweight and audit-friendly

---

## 📌 Supported Work Types (SaaS 1.0)

| Work Type | Description |
|---------|-------------|
| O&M | Orientation & Mobility Training |
| ADL | Daily Living Skills Training |

> ℹ️ This version focuses on O&M and ADL professionals.  
> Future versions will support fully customizable work categories.

---

## 🔒 Privacy & Security

- All query codes are encrypted and hashed
- Teachers never share login credentials with agencies
- Partners can only access authorized case records

---

## 🛠 Tech Stack

- Python / Flask
- SQLite / SQLAlchemy
- Flask-Mail (Email Reset System)
- Jinja2 Templates
- Railway Deployment Ready

---

## 🚀 Roadmap

| Version | Planned Features |
|--------|------------------|
| SaaS 1.0 | O&M & ADL working hour tracking |
| SaaS 1.5 | Customizable display names for work items |
| SaaS 2.0 | Fully dynamic multi-category work tracking |
| SaaS 3.0 | Multi-organization & team collaboration |

---

## 💡 Philosophy

Working-Hours-E was created to simplify professional service record keeping while maintaining privacy, clarity, and audit readiness —  
so professionals can focus on what truly matters: **serving people, not paperwork.**

---

## Developed by

A-kâu 阿猴 × Kim-chio 金蕉
Monkey & Banana Studio 🐒🍌

---

© 🐒🍌 猴蕉工作室 Monkey & Banana Studio  
Developed by A-kâu（阿猴）& Kim-chio（金蕉）  
All rights reserved.
