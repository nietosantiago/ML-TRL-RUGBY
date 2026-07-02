.PHONY: help setup db-init db-seed dev-backend dev-frontend scrape update validate

help:
	@echo "Comandos disponibles:"
	@echo "  make setup          Instala dependencias Python y Node"
	@echo "  make db-init        Crea la DB y aplica el schema"
	@echo "  make db-seed        Inserta datos de ejemplo"
	@echo "  make scrape         Ejecuta el scraper (requiere URL configurada)"
	@echo "  make update         Scraper + recalcular ELO + actualizar stats"
	@echo "  make validate       Backtesting de modelos"
	@echo "  make video-setup    Instala dependencias del pipeline de video"
	@echo "  make analyze VIDEO=partido.mp4 [MATCH_ID=42]   Detecta eventos en un video"
	@echo "  make db-migrate-events  Crea las tablas de análisis de video"
	@echo "  make dev-backend    Inicia el backend FastAPI (puerto 8000)"
	@echo "  make dev-frontend   Inicia el frontend Next.js (puerto 3000)"
	@echo "  make docker-up      Levanta todo con Docker Compose"
	@echo "  make docker-down    Baja los contenedores"

setup:
	pip install -r backend/requirements.txt
	cd frontend && npm install

db-init:
	python scripts/setup_db.py

db-seed:
	python scripts/seed_data.py

scrape:
	python scripts/scraper.py --season $(or $(SEASON),2024) --save-db

update:
	python scripts/update_data.py

validate:
	python -m models.validation --compare-all --train-seasons 2022 2023 --test-season 2024

video-setup:
	pip install -r video_analysis/requirements.txt

analyze:
	python scripts/analyze_video.py $(VIDEO) $(if $(MATCH_ID),--match-id $(MATCH_ID)) --api-url $(or $(API_URL),http://localhost:8000)

db-migrate-events:
	python scripts/migrate_video_events.py

dev-backend:
	uvicorn backend.app.main:app --reload --port 8000 --log-level info

dev-frontend:
	cd frontend && npm run dev

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f backend

db-shell:
	docker compose exec postgres psql -U trl_user -d trl_db

clean-models:
	rm -f data/models/*.pkl data/models/*.joblib
