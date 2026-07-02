"""
Deploy del backend a un Hugging Face Space (Docker).

Uso:
  HF_TOKEN=hf_xxx HF_SPACE_ID=usuario/trl-rugby-api python scripts/deploy_hf.py

Variables de entorno:
  HF_TOKEN            token de escritura de Hugging Face (obligatorio)
  HF_SPACE_ID         id del Space, ej. "usuario/trl-rugby-api" (obligatorio)
  DATABASE_URL        si está definida, se guarda como secret del Space
  ASYNC_DATABASE_URL  si está definida, se guarda como secret del Space

Sube: backend/ + data/models/ + .hf/Dockerfile (como Dockerfile raíz)
      + .hf/README.md (como README del Space).
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent

token = os.environ.get("HF_TOKEN")
space_id = os.environ.get("HF_SPACE_ID")
if not token or not space_id:
    sys.exit("ERROR: definí HF_TOKEN y HF_SPACE_ID en el entorno")

api = HfApi(token=token)

# 1. Crear el Space si no existe (Docker SDK, público)
api.create_repo(
    repo_id=space_id,
    repo_type="space",
    space_sdk="docker",
    exist_ok=True,
)
print(f"Space listo: https://huggingface.co/spaces/{space_id}")

# 2. Secrets del Space (solo si están en el entorno; persisten entre deploys)
for key in ("DATABASE_URL", "ASYNC_DATABASE_URL"):
    value = os.environ.get(key)
    if value:
        api.add_space_secret(repo_id=space_id, key=key, value=value.strip())
        print(f"Secret configurado: {key}")

# 3. Armar carpeta staging con el layout que espera el Space
with tempfile.TemporaryDirectory() as tmp:
    stage = Path(tmp) / "space"
    stage.mkdir()

    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    shutil.copytree(ROOT / "backend", stage / "backend", ignore=ignore)
    (stage / "data").mkdir()
    shutil.copytree(ROOT / "data" / "models", stage / "data" / "models")
    shutil.copy(ROOT / ".hf" / "Dockerfile", stage / "Dockerfile")
    shutil.copy(ROOT / ".hf" / "README.md", stage / "README.md")

    # 4. Subir (cada commit dispara un rebuild del Space)
    api.upload_folder(
        folder_path=str(stage),
        repo_id=space_id,
        repo_type="space",
        commit_message="deploy backend",
    )

owner, name = space_id.split("/")
subdomain = f"{owner}-{name}".replace("_", "-").replace(".", "-").lower()
print("Deploy subido. El Space se está construyendo.")
print(f"  Panel:  https://huggingface.co/spaces/{space_id}")
print(f"  API:    https://{subdomain}.hf.space")
print(f"  Health: https://{subdomain}.hf.space/health")
