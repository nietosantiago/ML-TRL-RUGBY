# TRL Rugby Analytics

Sistema completo de análisis estadístico, predicción y simulación para el **Torneo Regional del Litoral de Rugby** (Argentina).

## Arquitectura

```
TRL/
├── backend/          FastAPI + SQLAlchemy async (Python 3.12)
├── frontend/         Next.js 14 + TypeScript + Tailwind + Recharts
├── models/           ELO, Regresión Logística, XGBoost, Monte Carlo
├── scripts/          Scraper, setup DB, actualización automática
├── data/
│   ├── schemas/      Esquema PostgreSQL (init.sql)
│   ├── raw/          Datos crudos del scraper (no commiteados)
│   └── models/       Modelos entrenados .pkl (no commiteados)
```

## Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Base de datos | PostgreSQL 16 |
| Backend | FastAPI 0.115, SQLAlchemy 2.0, asyncpg |
| Modelos | scikit-learn, XGBoost, NumPy |
| Scraping | requests, BeautifulSoup4 |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, Recharts |
| Orquestación | Docker Compose |

---

## Setup rápido

### Opción 1: Docker (recomendado)

```bash
cp .env.example .env
# Editar .env con la URL real del torneo

docker compose up -d
# Seed con datos de ejemplo:
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

# 4. Seed con datos de ejemplo
make db-seed

# 5. Iniciar backend (en una terminal)
make dev-backend

# 6. Iniciar frontend (en otra terminal)
make dev-frontend
```

---

## Configurar el scraper

Editá `scripts/scraper.py` y cambiá:

```python
TARGET_URL = "https://TU_URL_AQUI.com"      # ← URL real del TRL
```

Luego ejecutá:
```bash
make scrape SEASON=2024
```

Para actualización automática diaria (cron):
```bash
# Agregar a crontab:
0 23 * * * cd /ruta/al/proyecto && make update >> logs/cron.log 2>&1
```

---

## Modelos predictivos

### 1. ELO Avanzado
- Rating inicial: 1500
- Ventaja de localía: +60 puntos ELO
- K-factor dinámico según margen de victoria
- Regresión a la media entre temporadas (30%)

### 2. Regresión Logística
Features:
- Diferencia de ELO (con localía)
- Forma últimos 5 partidos (ponderada)
- % victorias local/visitante
- Diferencia de puntos promedio
- Racha actual

### 3. XGBoost
- Mismo set de features + interacciones automáticas
- Búsqueda de hiperparámetros con RandomizedSearchCV
- Calibración de probabilidades (isotonic regression)

### Validación histórica (backtesting)

```bash
make validate
```

Ejecuta walk-forward CV sobre todas las temporadas disponibles y reporta:
- Log Loss (principal métrica)
- Accuracy
- Brier Score

El mejor modelo se selecciona automáticamente para producción.

---

## Simulación Monte Carlo

10.000+ iteraciones del resto de la temporada:

```python
from models.monte_carlo import MonteCarloSimulator, SimulationConfig

config = SimulationConfig(n_iterations=10_000)
sim = MonteCarloSimulator(config)
result = sim.simulate(standings, pending_matches)

# Output por equipo:
# - P(campeón)
# - P(clasificar a semis)
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
| Posiciones | `/standings` | Tabla completa + evolución ELO + gráfico |
| Partidos | `/matches` | Resultados, fixture y predicciones |
| Simulador | `/simulator` | Simulación interactiva con resultados fijados |

---

## Subir a GitHub

```bash
cd TRL
git init
git add .
git commit -m "feat: TRL Rugby Analytics — MVP completo"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/trl-rugby.git
git push -u origin main
```

> **Nota:** Los archivos `.env`, `data/raw/`, `data/models/` y `logs/` están en `.gitignore`
> y no se suben por seguridad/tamaño.

---

## Desarrollado con

- Python 3.12 · FastAPI · SQLAlchemy 2.0 · scikit-learn · XGBoost · NumPy
- Next.js 14 · TypeScript · Tailwind CSS · Recharts · TanStack Query
- PostgreSQL 16 · Docker
