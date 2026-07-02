"""
Analiza un video de partido y detecta situaciones de juego
(rucks, tackles, kicks, carries) con el pipeline de video_analysis.

USO:
  # Analizar y guardar eventos en JSON
  python scripts/analyze_video.py partido.mp4

  # Asociar a un partido de la DB e importar directo a la API
  python scripts/analyze_video.py partido.mp4 --match-id 42 --api-url http://localhost:8000

  # Video anotado para calibrar umbrales (dibuja detecciones)
  python scripts/analyze_video.py partido.mp4 --annotate debug.mp4

  # Modelo más preciso (recomendado con GPU) y más fps de muestreo
  python scripts/analyze_video.py partido.mp4 --model yolov8s.pt --sample-fps 10

Requiere: pip install -r video_analysis/requirements.txt
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from video_analysis.config import AnalysisConfig
from video_analysis.pipeline import analyze_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("analyze_video")


def import_to_api(api_url: str, payload: dict, match_id: int | None) -> None:
    import requests

    body = {**payload, "match_id": match_id}
    url = f"{api_url.rstrip('/')}/api/v1/analysis/import"
    logger.info(f"Importando a {url}...")
    resp = requests.post(url, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    logger.info(
        f"Importado: analysis_id={data['analysis_id']}, {data['n_events']} eventos"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Detección de situaciones de juego en video de rugby"
    )
    parser.add_argument("video", help="Ruta al video del partido")
    parser.add_argument("--out", help="Archivo JSON de salida (default: <video>.events.json)")
    parser.add_argument("--match-id", type=int, help="ID del partido en la DB para asociar")
    parser.add_argument("--api-url", help="URL del backend para importar (ej: http://localhost:8000)")
    parser.add_argument("--annotate", help="Escribir video anotado de debug en esta ruta")
    parser.add_argument("--model", default="yolov8n.pt", help="Modelo YOLO (yolov8n/s/m.pt)")
    parser.add_argument("--sample-fps", type=float, default=8.0, help="Frames analizados por segundo")
    parser.add_argument("--device", default=None, help="cpu | cuda | None (auto)")
    args = parser.parse_args()

    video_path = Path(args.video)
    out_path = Path(args.out) if args.out else video_path.with_suffix(".events.json")

    cfg = AnalysisConfig(
        model_name=args.model,
        sample_fps=args.sample_fps,
        device=args.device,
    )

    def show_progress(frac: float):
        print(f"\r  Procesando... {frac * 100:.0f}%", end="", flush=True)

    result = analyze_video(
        video_path,
        cfg=cfg,
        annotate_path=args.annotate,
        progress=show_progress,
    )
    print()

    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info(f"Eventos guardados en {out_path}")

    by_type: dict[str, int] = {}
    for e in result["events"]:
        by_type[e["event_type"]] = by_type.get(e["event_type"], 0) + 1
    logger.info(f"Resumen: {by_type or 'sin eventos'}")

    if args.api_url:
        import_to_api(args.api_url, result, args.match_id)
    else:
        logger.info(
            "Para importar al backend: python scripts/analyze_video.py "
            f"{video_path.name} --api-url http://localhost:8000"
            + (f" --match-id {args.match_id}" if args.match_id else "")
        )


if __name__ == "__main__":
    main()
