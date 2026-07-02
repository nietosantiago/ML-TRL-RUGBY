# Dockerfile para Hugging Face Spaces (se copia a la raíz del Space al deployar)
# El Space escucha en el puerto 7860 (default de HF, declarado en .hf/README.md)
FROM python:3.12-slim

# libgomp1: requerido por xgboost/scikit-learn en imágenes slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces recomienda correr como usuario UID 1000
RUN useradd -m -u 1000 user

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/raw data/processed logs && chown -R user:user /app

USER user

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
