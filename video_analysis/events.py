"""
Heurísticas de detección de situaciones de juego sobre detecciones trackeadas.

Este módulo es puro Python (sin ultralytics/torch) para poder testearse con
secuencias sintéticas. Recibe la lista de FrameData que produce el detector
y devuelve eventos: ruck, tackle, kick, carry.

Principios:
- Todas las distancias se normalizan por la altura mediana de jugador del
  frame (H), para ser robustas al zoom.
- Las velocidades se compensan por el movimiento de cámara restando el
  desplazamiento mediano de todos los jugadores entre frames consecutivos.
"""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Optional

from .config import AnalysisConfig
from .structures import Event, FrameData, TrackedPlayer


# ─── Preprocesamiento ─────────────────────────────────────────────────────────

class _Context:
    """Series derivadas de los frames: escalas, cámara, velocidades por track."""

    def __init__(self, frames: list[FrameData], cfg: AnalysisConfig):
        self.frames = frames
        self.cfg = cfg
        self.n = len(frames)

        # Escala H por frame (altura mediana de jugador, en píxeles)
        self.scales: list[float] = []
        for f in frames:
            heights = [p.h for p in f.players if p.h > 1]
            self.scales.append(
                median(heights) if len(heights) >= 3
                else f.frame_h * cfg.fallback_scale_frac
            )

        # Posición de cada track por índice de frame
        self.track_pos: dict[int, dict[int, TrackedPlayer]] = defaultdict(dict)
        for i, f in enumerate(frames):
            for p in f.players:
                self.track_pos[p.track_id][i] = p

        # Desplazamiento de cámara entre frame i-1 e i (mediana de los
        # desplazamientos de los tracks presentes en ambos)
        self.cam_dx: list[float] = [0.0] * self.n
        self.cam_dy: list[float] = [0.0] * self.n
        for i in range(1, self.n):
            dxs, dys = [], []
            for p in frames[i].players:
                prev = self.track_pos[p.track_id].get(i - 1)
                if prev is not None:
                    dxs.append(p.cx - prev.cx)
                    dys.append(p.cy - prev.cy)
            if len(dxs) >= 3:
                self.cam_dx[i] = median(dxs)
                self.cam_dy[i] = median(dys)

        # Velocidad relativa (compensada por cámara) de cada track, en H/s
        self._vel: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
        for tid, positions in self.track_pos.items():
            for i in positions:
                if i == 0 or (i - 1) not in positions:
                    continue
                dt = frames[i].t - frames[i - 1].t
                if dt <= 0:
                    continue
                cur, prev = positions[i], positions[i - 1]
                h = self.scales[i]
                vx = (cur.cx - prev.cx - self.cam_dx[i]) / dt / h
                vy = (cur.cy - prev.cy - self.cam_dy[i]) / dt / h
                self._vel[tid][i] = (vx, vy)

    def speed(self, tid: int, i: int) -> Optional[float]:
        """Velocidad (módulo, H/s) suavizada en una ventana corta."""
        win = self.cfg.velocity_smooth_window
        samples = [
            self._vel[tid][j]
            for j in range(max(0, i - win + 1), i + 1)
            if j in self._vel[tid]
        ]
        if not samples:
            return None
        vx = sum(s[0] for s in samples) / len(samples)
        vy = sum(s[1] for s in samples) / len(samples)
        return math.hypot(vx, vy)

    def dist(self, a: TrackedPlayer, b: TrackedPlayer, i: int) -> float:
        """Distancia entre centros en unidades H."""
        return math.hypot(a.cx - b.cx, a.cy - b.cy) / self.scales[i]

    def norm_xy(self, i: int, x: float, y: float) -> tuple[float, float]:
        f = self.frames[i]
        return (
            min(max(x / f.frame_w, 0.0), 1.0),
            min(max(y / f.frame_h, 0.0), 1.0),
        )


def _clusters(players: list[TrackedPlayer], link_dist_px: float) -> list[list[TrackedPlayer]]:
    """Agrupamiento single-linkage por distancia entre centros (union-find)."""
    n = len(players)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if math.hypot(players[i].cx - players[j].cx,
                          players[i].cy - players[j].cy) <= link_dist_px:
                parent[find(i)] = find(j)

    groups: dict[int, list[TrackedPlayer]] = defaultdict(list)
    for i, p in enumerate(players):
        groups[find(i)].append(p)
    return list(groups.values())


# ─── Rucks ────────────────────────────────────────────────────────────────────

class _ClusterCandidate:
    def __init__(self, i: int, t: float, cx: float, cy: float, size: int):
        self.first_i = i
        self.t_start = t
        self.t_last = t
        self.cx = cx
        self.cy = cy
        self.max_size = size
        self.sizes: list[int] = [size]
        self.positions: list[tuple[float, float]] = [(cx, cy)]


def _detect_rucks(ctx: _Context) -> list[Event]:
    cfg = ctx.cfg
    events: list[Event] = []
    live: list[_ClusterCandidate] = []

    def close(cand: _ClusterCandidate):
        duration = cand.t_last - cand.t_start
        if duration < cfg.ruck_min_duration:
            return
        mid = len(cand.positions) // 2
        cx, cy = cand.positions[mid]
        i_mid = min(cand.first_i + mid, ctx.n - 1)
        x, y = ctx.norm_xy(i_mid, cx, cy)
        conf = min(1.0, 0.4 + 0.05 * cand.max_size + 0.06 * duration)
        events.append(Event(
            event_type="ruck",
            t_start=cand.t_start,
            t_end=cand.t_last,
            confidence=conf,
            n_players=cand.max_size,
            x_norm=x, y_norm=y,
            meta={"mean_size": round(sum(cand.sizes) / len(cand.sizes), 1)},
        ))

    for i, f in enumerate(ctx.frames):
        h = ctx.scales[i]
        clusters = [
            c for c in _clusters(f.players, cfg.cluster_link_dist * h)
            if len(c) >= cfg.ruck_min_players
        ]

        # Filtrar clusters en movimiento (un maul avanza, un ruck no; acá
        # aceptamos ambos si el grupo se mueve lento)
        static_clusters = []
        for c in clusters:
            speeds = [s for p in c if (s := ctx.speed(p.track_id, i)) is not None]
            mean_speed = sum(speeds) / len(speeds) if speeds else 0.0
            if mean_speed <= cfg.ruck_max_speed:
                static_clusters.append(c)

        matched: set[int] = set()
        for c in static_clusters:
            ccx = sum(p.cx for p in c) / len(c)
            ccy = sum(p.cy for p in c) / len(c)
            best, best_d = None, None
            for k, cand in enumerate(live):
                if k in matched:
                    continue
                d = math.hypot(cand.cx - ccx, cand.cy - ccy) / h
                if d <= 1.5 and (best_d is None or d < best_d):
                    best, best_d = k, d
            if best is not None:
                cand = live[best]
                matched.add(best)
                cand.t_last = f.t
                cand.cx, cand.cy = ccx, ccy
                cand.max_size = max(cand.max_size, len(c))
                cand.sizes.append(len(c))
                cand.positions.append((ccx, ccy))
            else:
                live.append(_ClusterCandidate(i, f.t, ccx, ccy, len(c)))
                matched.add(len(live) - 1)

        # Cerrar candidatos que no se vieron por más del gap tolerado
        still_alive = []
        for cand in live:
            if f.t - cand.t_last > cfg.ruck_gap_tolerance:
                close(cand)
            else:
                still_alive.append(cand)
        live = still_alive

    for cand in live:
        close(cand)
    return events


# ─── Tackles ──────────────────────────────────────────────────────────────────

def _median_height(ctx: _Context, tid: int, i: int, lookback_s: float = 2.0) -> Optional[float]:
    t_now = ctx.frames[i].t
    hs = [
        p.h for j, p in ctx.track_pos[tid].items()
        if j <= i and t_now - ctx.frames[j].t <= lookback_s
    ]
    return median(hs) if hs else None


def _is_fallen(ctx: _Context, tid: int, i: int) -> bool:
    p = ctx.track_pos[tid].get(i)
    if p is None or p.h <= 0:
        return False
    if p.w / p.h >= ctx.cfg.tackle_fall_aspect:
        return True
    med_h = _median_height(ctx, tid, i)
    return med_h is not None and p.h < ctx.cfg.tackle_fall_height_ratio * med_h


def _detect_tackles(ctx: _Context) -> list[Event]:
    cfg = ctx.cfg
    events: list[Event] = []
    # (tid_a, tid_b) -> frame del último contacto evaluado, para no re-disparar
    pair_seen: dict[tuple[int, int], float] = {}

    for i in range(1, ctx.n):
        f = ctx.frames[i]
        players = f.players
        for a_idx in range(len(players)):
            for b_idx in range(a_idx + 1, len(players)):
                a, b = players[a_idx], players[b_idx]
                if ctx.dist(a, b, i) > cfg.tackle_contact_dist:
                    continue

                key = (min(a.track_id, b.track_id), max(a.track_id, b.track_id))
                if f.t - pair_seen.get(key, -1e9) < cfg.tackle_cooldown:
                    continue

                # Velocidad de aproximación: cuánto cayó la distancia en ~0.6s
                j = i
                t_back = f.t - 0.6
                while j > 0 and ctx.frames[j - 1].t >= t_back:
                    j -= 1
                pa, pb = ctx.track_pos[a.track_id].get(j), ctx.track_pos[b.track_id].get(j)
                if pa is None or pb is None:
                    continue
                dt = f.t - ctx.frames[j].t
                if dt <= 0:
                    continue
                approach = (ctx.dist(pa, pb, j) - ctx.dist(a, b, i)) / dt
                if approach < cfg.tackle_approach_speed:
                    continue

                pair_seen[key] = f.t

                # Confirmar caída de alguno de los dos en la ventana siguiente
                fell = False
                k = i
                while k < ctx.n and ctx.frames[k].t - f.t <= cfg.tackle_fall_window:
                    if _is_fallen(ctx, a.track_id, k) or _is_fallen(ctx, b.track_id, k):
                        fell = True
                        break
                    k += 1
                if not fell:
                    continue

                mx, my = (a.cx + b.cx) / 2, (a.cy + b.cy) / 2

                # Anti-duplicado espacial contra tackles recientes
                dup = any(
                    f.t - e.t_start < cfg.tackle_cooldown
                    and e.x_norm is not None
                    and math.hypot(
                        (e.x_norm * f.frame_w) - mx,
                        (e.y_norm * f.frame_h) - my,
                    ) / ctx.scales[i] < cfg.tackle_cooldown_dist
                    for e in events
                )
                if dup:
                    continue

                x, y = ctx.norm_xy(i, mx, my)
                conf = min(1.0, 0.5 + 0.08 * min(approach, 4.0))
                events.append(Event(
                    event_type="tackle",
                    t_start=f.t,
                    confidence=conf,
                    n_players=2,
                    x_norm=x, y_norm=y,
                    meta={
                        "tracks": list(key),
                        "approach_speed": round(approach, 2),
                    },
                ))
    return events


# ─── Carries ──────────────────────────────────────────────────────────────────

def _detect_carries(ctx: _Context) -> list[Event]:
    cfg = ctx.cfg
    events: list[Event] = []

    # 1) Con pelota: jugador más cercano a la pelota, moviéndose rápido
    runs: dict[int, dict] = {}   # tid -> run activa
    last_carry: dict[int, float] = {}

    def close_run(tid: int, run: dict):
        duration = run["t_last"] - run["t_start"]
        if duration < cfg.carry_min_duration:
            return
        if run["t_start"] - last_carry.get(tid, -1e9) < cfg.carry_cooldown:
            return
        last_carry[tid] = run["t_last"]
        i_mid = run["i_mid"]
        x, y = ctx.norm_xy(i_mid, run["mx"], run["my"])
        events.append(Event(
            event_type="carry",
            t_start=run["t_start"],
            t_end=run["t_last"],
            confidence=min(1.0, 0.5 + 0.15 * duration),
            n_players=1,
            x_norm=x, y_norm=y,
            meta={"track": tid, "method": run["method"],
                  "max_speed": round(run["max_speed"], 2)},
        ))

    for i, f in enumerate(ctx.frames):
        h = ctx.scales[i]
        carrier: Optional[int] = None

        if f.ball is not None:
            best_d = None
            for p in f.players:
                d = math.hypot(p.cx - f.ball.cx, p.cy - f.ball.cy) / h
                if d <= cfg.possession_dist and (best_d is None or d < best_d):
                    carrier, best_d = p.track_id, d

        active_this_frame: set[int] = set()

        if carrier is not None:
            spd = ctx.speed(carrier, i)
            if spd is not None and spd >= cfg.carry_min_speed:
                p = ctx.track_pos[carrier][i]
                run = runs.get(carrier)
                if run is None or run["method"] != "ball":
                    runs[carrier] = run = {
                        "t_start": f.t, "t_last": f.t, "method": "ball",
                        "mx": p.cx, "my": p.cy, "i_mid": i, "max_speed": spd,
                    }
                run["t_last"] = f.t
                run["max_speed"] = max(run["max_speed"], spd)
                active_this_frame.add(carrier)

        # 2) Fallback sin pelota: corredor rápido y aislado (corte de línea)
        if f.ball is None:
            for p in f.players:
                spd = ctx.speed(p.track_id, i)
                if spd is None or spd < cfg.breakaway_speed:
                    continue
                nearest = min(
                    (ctx.dist(p, q, i) for q in f.players if q.track_id != p.track_id),
                    default=1e9,
                )
                if nearest < cfg.breakaway_isolation:
                    continue
                run = runs.get(p.track_id)
                if run is None or run["method"] != "breakaway":
                    runs[p.track_id] = run = {
                        "t_start": f.t, "t_last": f.t, "method": "breakaway",
                        "mx": p.cx, "my": p.cy, "i_mid": i, "max_speed": spd,
                    }
                run["t_last"] = f.t
                run["max_speed"] = max(run["max_speed"], spd)
                active_this_frame.add(p.track_id)

        # Cerrar runs que se cortaron (tolerancia de 2 frames de muestreo)
        stale = [
            tid for tid, run in runs.items()
            if tid not in active_this_frame and f.t - run["t_last"] > 0.3
        ]
        for tid in stale:
            run = runs.pop(tid)
            min_dur = (cfg.breakaway_min_duration if run["method"] == "breakaway"
                       else cfg.carry_min_duration)
            if run["t_last"] - run["t_start"] >= min_dur:
                close_run(tid, run)

    for tid, run in runs.items():
        min_dur = (cfg.breakaway_min_duration if run["method"] == "breakaway"
                   else cfg.carry_min_duration)
        if run["t_last"] - run["t_start"] >= min_dur:
            close_run(tid, run)
    return events


# ─── Kicks ────────────────────────────────────────────────────────────────────

def _detect_kicks(ctx: _Context) -> list[Event]:
    cfg = ctx.cfg
    events: list[Event] = []

    # Serie temporal de la pelota (índices de frame donde fue detectada)
    ball_idx = [i for i, f in enumerate(ctx.frames) if f.ball is not None]
    last_kick = -1e9

    for a, b in zip(ball_idx, ball_idx[1:]):
        fa, fb = ctx.frames[a], ctx.frames[b]
        dt = fb.t - fa.t
        if dt <= 0 or dt > 0.5:   # gap muy grande, la velocidad no es confiable
            continue
        h = ctx.scales[b]
        cam_dx = sum(ctx.cam_dx[a + 1:b + 1])
        cam_dy = sum(ctx.cam_dy[a + 1:b + 1])
        speed = math.hypot(
            fb.ball.cx - fa.ball.cx - cam_dx,
            fb.ball.cy - fa.ball.cy - cam_dy,
        ) / dt / h
        if speed < cfg.kick_speed_min:
            continue
        if fb.t - last_kick < cfg.kick_cooldown:
            continue

        # La pelota tiene que haber estado junto a un jugador justo antes...
        near_before = any(
            math.hypot(p.cx - fa.ball.cx, p.cy - fa.ball.cy) / ctx.scales[a]
            <= cfg.kick_near_player_dist
            for p in fa.players
        )
        if not near_before:
            continue

        # ...y alejarse de todos (o salir de cámara) inmediatamente después
        separated = False
        for j in ball_idx:
            if not (fb.t < ctx.frames[j].t <= fb.t + cfg.kick_separation_window):
                continue
            fj = ctx.frames[j]
            nearest = min(
                (math.hypot(p.cx - fj.ball.cx, p.cy - fj.ball.cy) / ctx.scales[j]
                 for p in fj.players),
                default=1e9,
            )
            if nearest >= cfg.kick_separation_dist:
                separated = True
                break
        else:
            # sin detecciones de pelota en la ventana → salió de cámara: válido
            has_future = any(
                fb.t < ctx.frames[j].t <= fb.t + cfg.kick_separation_window
                for j in ball_idx
            )
            separated = not has_future

        if not separated:
            continue

        last_kick = fb.t
        x, y = ctx.norm_xy(a, fa.ball.cx, fa.ball.cy)
        events.append(Event(
            event_type="kick",
            t_start=fa.t,
            confidence=min(1.0, 0.45 + 0.05 * min(speed, 10.0)),
            x_norm=x, y_norm=y,
            meta={"ball_speed": round(speed, 2)},
        ))
    return events


# ─── API pública ──────────────────────────────────────────────────────────────

def extract_events(frames: list[FrameData],
                   cfg: Optional[AnalysisConfig] = None) -> list[Event]:
    """Extrae rucks, tackles, kicks y carries de una secuencia de frames."""
    if cfg is None:
        cfg = AnalysisConfig()
    if len(frames) < 3:
        return []

    ctx = _Context(frames, cfg)
    events = (
        _detect_rucks(ctx)
        + _detect_tackles(ctx)
        + _detect_carries(ctx)
        + _detect_kicks(ctx)
    )
    events.sort(key=lambda e: e.t_start)
    return events
