<![CDATA[<div align="center">

# 🏉 TRL Rugby Analytics

**Predicción de partidos y simulación de temporada para el Torneo Regional del Litoral**

[![Live App](https://img.shields.io/badge/App-ml--trl--rugby.vercel.app-22c55e?style=for-the-badge&logo=vercel)](https://ml-trl-rugby.vercel.app)
[![API](https://img.shields.io/badge/API-Render-4f46e5?style=for-the-badge&logo=render)](https://trl-rugby-api.onrender.com/docs)
[![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=for-the-badge&logo=python)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-14-black?style=for-the-badge&logo=next.js)](https://nextjs.org)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

</div>

---

## ¿Qué es el TRL?

El **Torneo Regional del Litoral** es uno de los torneos de rugby más importantes de Argentina, disputado entre clubes de Santa Fe, Entre Ríos y Rosario. Participan **10 equipos** en una fase regular de 18 fechas, seguida de una fase de playoffs con los 4 mejores clasificados.

Equipos participantes 2026: Santa Fe RC · Club Universitario · Old Resian · Gimnasia y Esgrima (GER) · Paraná Rowing · Estudiantes Paraná · CRAI · Duendes · Jockey Club V. del Tuerto · Jockey Club Rosario

---

## ¿Qué hace esta app?

Esta plataforma usa **datos históricos del TRL desde 2015** y modelos de Machine Learning para responder tres preguntas:

> **¿Quién va a ganar el próximo partido?**
> → La app predice la probabilidad de victoria para cada equipo antes de que se juegue.

> **¿Cómo va a terminar la temporada?**
> → Simulando 10.000 veces el resto del torneo, la app muestra qué chance tiene cada equipo de clasificar a semis o salir campeón.

> **¿Qué pasaría si...?**
> → El simulador interactivo permite fijar resultados hipotéticos ("¿qué pasa si Duendes pierde las próximas 3?") y ver cómo cambia la tabla.

---

## Funcionalidades principales

| Sección | Qué hace |
|---------|----------|
| **Dashboard** | Tabla de posiciones en tiempo real + probabilidades de clasificación de cada equipo |
| **Partidos** | Fixture completo, resultados jugados y predicción ELO para partidos pendientes |
| **Posiciones** | Tabla detallada con evolución del rating ELO a lo largo de la temporada |
| **Simulador** | Simulación Monte Carlo interactiva — fijá resultados y mirá cómo cambian las chances |

---

## Modelos de predicción

La app implementa **tres modelos independientes**, cada uno con un enfoque distinto:

### 1. Sistema ELO
El mismo algoritmo que usa el ajedrez mundial, adaptado al rugby. Cada equipo tiene un *rating* que sube al ganar y baja al perder, considerando la diferencia de puntos y la localía.

- Rating inicial: 1.500
- Ventaja de local: +50 puntos ELO
- Los ratings se actualizan después de cada partido jugado
- Entre temporadas, los ratings convergen al promedio (evita que el pasado pese demasiado)

### 2. Regresión Logística
Modelo estadístico supervisado entrenado con ~1.161 partidos históricos (2015–2025). Combina múltiples variables para predecir el resultado:

- Diferencia de ELO entre equipos
- Porcentaje de victorias como local / visitante
- Promedio de puntos anotados y recibidos
- Forma reciente (últimos 5 partidos)
- Racha actual de victorias o derrotas
- Historial de enfrentamientos directos (H2H)

### 3. XGBoost
Gradient Boosting sobre las mismas 22 variables. Captura relaciones complejas que la regresión lineal no detecta, como la interacción entre localía y momento de forma.

---

## Rendimiento real de los modelos

> Entrenados con datos 2015–2025 · Testeados con los 25 partidos jugados de 2026

| Modelo | Accuracy (histórico) | Accuracy (2026 real) | Brier Score |
|--------|---------------------:|---------------------:|------------:|
| ELO | 71.1% | **68.0%** | 0.268 |
| XGBoost | **75.7%** | 64.0% | **0.218** |
| Logistic | En revisión | — | — |

**Lectura:** El ELO, siendo el modelo más simple, generalizó mejor a datos nuevos (68% en 2026). XGBoost muestra la mejor *calibración probabilística* (Brier Score 0.218), lo que significa que sus probabilidades son más precisas aunque acierte menos partidos individuales. La regresión logística está en revisión por un problema de desbalance de clases con los empates (solo 1.5% del dataset histórico).

---

## Actualización automática de datos

Los resultados se actualizan **automáticamente** tres veces por semana (lunes, miércoles y viernes) mediante un pipeline en GitHub Actions:

```
scraper.py        →  Descarga resultados de rugbyarchive.net
seed_data.py      →  Actualiza la base de datos PostgreSQL
load_fixture.py   →  Mantiene el fixture oficial intacto
train_models.py   →  Re-entrena XGBoost y Logistic con los nuevos datos
commit models     →  Los modelos .pkl quedan versionados en el repo
```

También puede ejecutarse manualmente desde GitHub → Actions → *"Actualizar datos TRL"* → Run workflow.

---

## Campeones históricos TRL

| Año | Campeón |
|-----|---------|
| 2015 | Duendes RC |
| 2016 | Duendes RC |
| 2017 | Jockey Club Rosario |
| 2018 | Duendes RC |
| 2019 | Old Resian |
| 2021 | Duendes RC |
| 2022 | Gimnasia y Esgrima (GER) |
| 2023 | Estudiantes Paraná |
| 2024 | Jockey Club Rosario |
| 2025 | Jockey Club Rosario |
| 2026 | 🏆 En curso... |

---

## Stack tecnológico

```
Frontend          Backend           Datos & ML         Infraestructura
──────────        ──────────        ──────────         ──────────
Next.js 14        FastAPI           PostgreSQL 16      Vercel (frontend)
TypeScript        SQLAlchemy 2.0    scikit-learn       Render (backend + DB)
Tailwind CSS      asyncpg           XGBoost            GitHub Actions (CI)
Recharts          psycopg2          NumPy / Pandas
TanStack Query    Python 3.11       ELO custom model
```

---

## Estructura del proyecto

```
TRL/
├── backend/                 API REST (FastAPI)
│   ├── app/
│   │   ├── routers/         Endpoints: matches, teams, standings, predict, simulate
│   │   ├── models/          Schemas Pydantic
│   │   └── main.py          App entry point
│   └── requirements.txt
│
├── frontend/                Interfaz web (Next.js)
│   └── src/
│       ├── app/             Páginas: dashboard, matches, standings, simulator
│       ├── components/      MatchCard, ProbabilityBar, StandingsTable, etc.
│       └── lib/             API client, tipos TypeScript
│
├── models/                  Lógica de ML (agnóstica al framework)
│   ├── elo_model.py         Sistema ELO con localía y decay
│   ├── logistic_model.py    Regresión Logística calibrada
│   ├── xgboost_model.py     XGBoost con calibración isotónica
│   ├── monte_carlo.py       Simulador Monte Carlo
│   └── feature_engineering.py  22 features para los modelos supervisados
│
├── scripts/                 Pipeline de datos
│   ├── scraper.py           Scraping de rugbyarchive.net
│   ├── seed_data.py         Carga histórica + cálculo ELO
│   ├── load_fixture_2026.py Fixture oficial del torneo
│   └── train_models.py      Entrenamiento y guardado de modelos
│
├── data/
│   ├── schemas/init.sql     Esquema PostgreSQL completo
│   └── models/              Modelos entrenados (.pkl, versionados)
│
└── .github/workflows/
    └── update-data.yml      Automatización Mon/Mié/Vie 20:00 hs AR
```

---

## API Reference

Documentación interactiva disponible en: [`/docs`](https://trl-rugby-api.onrender.com/docs)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/v1/teams/` | Lista de equipos con stats |
| `GET` | `/api/v1/teams/{id}/elo-history` | Historial de rating ELO |
| `GET` | `/api/v1/matches/` | Fixture completo con filtros |
| `GET` | `/api/v1/standings/` | Tabla de posiciones actual |
| `GET` | `/api/v1/standings/evolution` | Evolución por ronda |
| `POST` | `/api/v1/predict/match` | Predicción de un partido |
| `POST` | `/api/v1/simulate/season` | Simulación Monte Carlo |
| `POST` | `/api/v1/simulate/custom` | Simulación con resultados fijos |

---

## Setup local

**Prerequisitos:** Python 3.11+, Node 20+, PostgreSQL 16

```bash
# 1. Clonar el repo
git clone https://github.com/nietosantiago/ML-TRL-RUGBY.git
cd ML-TRL-RUGBY

# 2. Backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # configurar DB_HOST, DB_NAME, etc.
uvicorn app.main:app --reload

# 3. Inicializar base de datos
psql -U postgres -f data/schemas/init.sql

# 4. Descargar datos históricos y cargar en DB
python scripts/scraper.py --all
python scripts/seed_data.py
python scripts/load_fixture_2026.py

# 5. Entrenar modelos ML
python scripts/train_models.py

# 6. Frontend (en otra terminal)
cd frontend
npm install
npm run dev
```

Accedés en: `http://localhost:3000` · API docs: `http://localhost:8000/docs`

---

## Fuente de datos

Los datos provienen de la API de [rugbyarchive.net](http://rugbyarchive.net) — base de datos global de rugby con resultados históricos del TRL desde 2015.

- **Competición ID:** 121 (TRL)
- **Temporadas:** 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026
- **Total histórico:** ~1.186 partidos jugados

---

<div align="center">

Desarrollado por **Santiago Nieto** · Argentina 🇦🇷

*Datos de* [rugbyarchive.net](http://rugbyarchive.net) · *Deploy en* [Vercel](https://vercel.com) *+* [Render](https://render.com)

</div>
]]>
