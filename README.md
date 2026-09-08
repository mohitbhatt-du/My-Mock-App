# 🚀 Analytics OS | IBPS SO IT Officer Mains - Mock Exam & Performance Platform

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%252B-blue?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Backend-green?style=for-the-badge&logo=flask&logoColor=white)
![Chart.js](https://img.shields.io/badge/Chart.js-Analytics-orange?style=for-the-badge&logo=chart.js&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)
[![Live Demo](https://img.shields.io/badge/Live-Website-emerald?style=for-the-badge&logo=render&logoColor=white)](https://my-mock-app.onrender.com)

A professional, automated mock exam operating system and performance dashboard built specifically for **IBPS SO IT Officer (Scale-I)** and technical banking examination preparation.

</div>

---

## 🌟 Overview

**ExamMatrix IT** is designed to bridge the gap between static question banks and dynamic performance tracking. Moving away from manual file management and traditional PDF scoring, this platform provides a robust server-backed, distraction-free environment to take daily IT Officer full-length mock exams, visualize core technical strengths, and track your readiness for competitive IT mains examinations.

---

## ✨ Key Features

*   📊 **Interactive Performance Analytics**: Powered by Chart.js to visualize score trends, accuracy distribution (Correct vs. Incorrect vs. Skipped), and overall growth over time.
*   🧠 **Topic Mastery Breakdown**: Automatically aggregate performance across core IT syllabus pillars (DBMS, Data Structures, Computer Networks, Operating Systems, Software Engineering, OOPs, and Banking Cyber Security).
*   ⚡ **Integrated Quiz Hub**: Scan, launch, and complete day-wise mock papers directly within a clean, fullscreen exam player interface.
*   💾 **Zero-Click Auto-Save & Isolation**: Results are dynamically tracked and securely saved client-side/server-side per session, providing a multi-user ready experience.
*   📄 **Print & PDF Optimization**: Custom print-ready CSS rules that eliminate blank page layout bugs when exporting test reviews.
*   🗑️ **Progress Management**: Clean UI utility to reset mock ledgers and start fresh revision cycles.

---

## 🛠️ Tech Stack

*   **Frontend**: HTML5, Modern CSS3 (Glassmorphism UI, Responsive Grids), JavaScript (ES6+).
*   **Visualizations & UI Assets**: Chart.js, Lucide Icons, Google Fonts (Inter).
*   **Backend**: Python Flask (RESTful architecture, automated directory scanning, regex metadata extraction).
*   **Production Deployment**: WSGI compatible (Waitress / Gunicorn) for seamless cloud hosting (Render, PythonAnywhere, etc.).
* **Simplicity**: Avoids over-engineering by using a straightforward tech stack to prioritize a comprehensive and accessible IT question bank.

---


## 📂 Project Directory Structure

```text
/My-Mock-App
│
├── app.py                  # Flask backend server & API routing
├── index.html              # Main Analytics OS Dashboard & Quiz Hub
├── requirements.txt        # Python package dependencies
├── visitors.json           # Unique visitor IP ledger
│
├── /Mock_Pages             # Directory containing day-wise HTML quiz modules
│   ├── Day_1_Quiz.html
│   ├── Day_2_Quiz.html
│   └── ...
│
└── /Result                 # Local/Cloud data records
```

## 💡 Developer Disclaimer

* This project was built in the trenches to solve a personal exam preparation problem not to win architectural awards. If you look under the hood and find messy scripts, spaghetti DOM manipulation, or unconventional Flask routes, congratulations! You've found a feature built entirely out of caffeine, deadlines, and pure survival instinct. Pull requests for cleaner code are welcome! 🚀