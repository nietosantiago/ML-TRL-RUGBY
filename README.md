# TRL Rugby Analytics

Sistema completo de análisis estadístico, predicción y simulación para el **Torneo Regional del Litoral de Rugby** (Argentina).

Cubre temporadas **2015–2026** con datos reales extraídos de [rugbyarchive.net](http://rugbyarchive.net).

## Arquitectura

```
TRL/
├── backend/          FastAPI + SQLAlchemy async (Python 3.12)
├── frontend/         Next.js 14 + TypeScript + Tailwind + Recharts
├── models/           ELO, Regresión Logística, XGBoost, Monte Carlo
├── scripts/          Scraper, setup DB, seed con datos reales
├── data/
│   ├── schemas/      Esquema PostgreSQL (init.sql)
│   ├── raw/          Datos crudos del scraper (no commiteados, ~470 KB)
│   └── models/       Modelos entrenados .pkl (no commiteados)
```

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Base de datos | PostgreSQL 16 |
| Backend | FastAPI 0.115, SQLAlchemy 2.0, asyncpg |
| Modelos | scikit-learn, XGBoost, NumPy |
| Scraping | urllib (stdlib, sin dependencias externas) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| Orquestación | Docker Compose |

---

## Setup rápido

### Opción 1: Docker (recomendado)

```bash
cp .env.example .env
docker compose up -d

# 1. Descargar datos reales del TRL (2015–2026)
docker compose exec backend python scripts/scraper.py --all

# 2. Cargar en la DB + calcular ELO histórico
docker compose exec backend python scripts/seed_data.py
```

Accedés en:
- **Frontend:** http://localhost:3000
- **API docs:** http://localhost:8000/docs

---

### Opción 2: Local (sin Docker)

**Prerequisitos:** Python 3.12+, Node 20+, PostgreSQL 16

```bash
# 1. Instalar dependencias
make setup

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales de PostgreSQL

# 3. Crear base de datos
make db-init

# 4. Descargar todos los datos históricos (2015–2026)
python scripts/scraper.py --all

# 5. Cargar datos reales + calcular ELO desde 2015
python scripts/seed_data.py

# 6. Iniciar backend (en una terminal)
make dev-backend

# 7. Iniciar frontend (en otra terminal)
make dev-frontend
```

---

## Fuente de datos

Los datos provienen de la API interna de [rugbyarchive.net](http://rugbyarchive.net):

```
http://rugbyarchive.net/api/stagionicompetizione/121/stagione/{year}/?cultura=en
```

- **Competición:** TRL (ID 121)
- **Temporadas disponibles:** 2015, 2016, 2017, 2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026
- **Total histórico:** ~1.176 partidos jugados
- **Actualización:** `python scripts/scraper.py --season 2026 --save-db`

Para actualización automática diaria:
```bash
# Agregar a crontab:
0 23 * * * cd /ruta/al/proyecto && make update >> logs/cron.log 2>&1
```

---

## Modelos predictivos

### 1. ELO Avanzado
- Rating inicial: 1500, entrenado con partidos 2015–2025
- Ventaja de localía: +60 puntos ELO
- K-factor dinámico según margen de victoria: `K × ln(|diff|+1) / ln(2)`
- Regresión a la media entre temporadas (30%)
- Campeones históricos aprendidos: Duendes (×4), Jockey Club Rosario (×2), G.E.R., Old Resian, Estudiantes Paraná

### 2. Regresión Logística (calibrada)
Features (22 en total):
- Diferencia de ELO (con localía)
- Forma últimos 5 partidos (ponderada)
- % victorias local/visitante
- Diferencia de puntos promedio
- Racha actual, H2H win rate

### 3. XGBoost
- Mismo set de features + interacciones automáticas
- Búsqueda de hiperparámetros con RandomizedSearchCV
- Calibración de probabilidades (isotonic regression)

### Validación histórica (backtesting)

```bash
make validate
```

Ejecuta walk-forward CV sobre 2015–2025 y reporta:
- Log Loss · Accuracy · Brier Score

---

## Simulación Monte Carlo

10.000+ iteraciones del resto de la temporada 2026:

```python
from models.monte_carlo import MonteCarloSimulator, SimulationConfig

config = SimulationConfig(n_iterations=10_000)
sim = MonteCarloSimulator(config)
result = sim.simulate(standings, pending_matches)

# Output por equipo:
# - P(campeón), P(clasificar a semis)
# - Distribución de posiciones (histograma)
# - Puntos finales: media, p5, p25, p50, p75, p95
```

---

## API Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/api/v1/teams/` | Lista de equipos |
| GET | `/api/v1/teams/{id}/elo-history` | Historial ELO |
| GET | `/api/v1/matches/` | Partidos (con filtros) |
| GET | `/api/v1/standings/` | Tabla de posiciones |
| GET | `/api/v1/standings/evolution` | Evolución por ronda |
| POST | `/api/v1/predict/match` | Predicción de partido |
| POST | `/api/v1/simulate/season` | Simulación Monte Carlo |
| POST | `/api/v1/simulate/custom` | Simulación con resultados fijos |

Documentación interactiva: http://localhost:8000/docs

---

## Frontend

| Página | URL | Descripción |
|--------|-----|-------------|
| Dashboard | `/` | Tabla + probabilidades + últimos resultados |
| Posiciones | `/standings` | Tabla completa + evolución ELO |
| Partidos | `/matches` | Resultados, fixture y predicciones ELO |
| Simulador | `/simulator` | Simulación interactiva con resultados fijados |

---

## Campeones históricos TRL

| Año | Campeón |
|-----|---------|
| 2015 | Duendes |
| 2016 | Duendes |
| 2017 | Jockey Club Rosario |
| 2018 | Duendes |
| 2019 | Old Resian |
| 2021 | Duendes |
| 2022 | G.E.R. |
| 2023 | Estudiantes Paraná |
| 2024 | Jockey Club Rosario |
| 2025 | Jockey Club Rosario |
| 2026 | En curso |

---

## Desarrollado con

- Python 3.12 · FastAPI · SQLAlchemy 2.0 · scikit-learn · XGBoost · NumPy
- Next.js 14 · TypeScript · Tailwind CSS · Recharts · TanStack Query
- PostgreSQL 16 · Docker
