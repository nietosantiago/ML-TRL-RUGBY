"""
Tests sintéticos de las heurísticas de eventos (sin video ni YOLO).

Ejecutar desde la raíz del proyecto:
    python -m video_analysis.test_events
"""

from .config import AnalysisConfig
from .events import extract_events
from .structures import BallDetection, FrameData, TrackedPlayer

FPS = 8.0
W, H = 1280, 720
PH = 80.0   # altura de jugador en píxeles → escala H


def player(tid, x, y, w=32.0, h=PH):
    return TrackedPlayer(track_id=tid, cx=x, cy=y, w=w, h=h, conf=0.9)


def background_players(offset=0.0):
    """Jugadores estáticos para estabilizar escala y compensación de cámara."""
    return [
        player(90, 100 + offset, 600),
        player(91, 300 + offset, 620),
        player(92, 1150 + offset, 580),
        player(93, 1000 + offset, 150),
    ]


def make_frames(n, build):
    frames = []
    for i in range(n):
        t = i / FPS
        f = FrameData(index=i, t=t, frame_w=W, frame_h=H)
        build(i, t, f)
        frames.append(f)
    return frames


def test_ruck():
    """6 jugadores aglomerados y estáticos durante 3s → un ruck."""
    def build(i, t, f):
        f.players.extend(background_players())
        cx, cy = 640, 360
        offsets = [(-60, -20), (0, -30), (60, -20), (-40, 25), (10, 30), (55, 20)]
        for k, (dx, dy) in enumerate(offsets):
            f.players.append(player(10 + k, cx + dx, cy + dy))

    events = extract_events(make_frames(30, build))
    rucks = [e for e in events if e.event_type == "ruck"]
    assert len(rucks) == 1, f"esperaba 1 ruck, hubo {len(rucks)}: {events}"
    r = rucks[0]
    assert r.n_players >= 6
    assert r.t_end - r.t_start >= 1.5
    print(f"  ruck OK: {r.n_players} jugadores, {r.t_end - r.t_start:.1f}s, conf={r.confidence:.2f}")


def test_tackle():
    """Dos jugadores convergen rápido, uno cae → un tackle."""
    def build(i, t, f):
        f.players.extend(background_players())
        # se acercan desde 400px hasta contacto en ~1s, luego uno cae
        gap = max(400 - i * 50, 10)
        f.players.append(player(1, 640 - gap / 2, 360))
        if gap > 20:
            f.players.append(player(2, 640 + gap / 2, 360))
        else:
            # caído: bbox ancho y bajo
            f.players.append(player(2, 640 + gap / 2, 390, w=100.0, h=50.0))

    events = extract_events(make_frames(24, build))
    tackles = [e for e in events if e.event_type == "tackle"]
    assert len(tackles) == 1, f"esperaba 1 tackle, hubo {len(tackles)}: {events}"
    print(f"  tackle OK: t={tackles[0].t_start:.2f}s, conf={tackles[0].confidence:.2f}")


def test_carry():
    """Jugador corre con la pelota 2s → un carry (método ball)."""
    def build(i, t, f):
        f.players.extend(background_players())
        x = 200 + i * 30    # 240 px/s = 3 H/s
        f.players.append(player(5, x, 300))
        f.ball = BallDetection(cx=x + 20, cy=310, conf=0.6)

    events = extract_events(make_frames(20, build))
    carries = [e for e in events if e.event_type == "carry"]
    assert len(carries) == 1, f"esperaba 1 carry, hubo {len(carries)}: {events}"
    assert carries[0].meta["method"] == "ball"
    print(f"  carry OK: {carries[0].t_end - carries[0].t_start:.1f}s, conf={carries[0].confidence:.2f}")


def test_kick():
    """Pelota junto a un jugador sale despedida y se aleja de todos → un kick."""
    def build(i, t, f):
        f.players.extend(background_players())
        f.players.append(player(7, 400, 400))
        if i < 8:
            f.ball = BallDetection(cx=420, cy=410, conf=0.6)   # en manos
        else:
            # vuela a ~90 px/frame = 720 px/s = 9 H/s
            f.ball = BallDetection(cx=420 + (i - 7) * 90, cy=410 - (i - 7) * 30, conf=0.5)

    events = extract_events(make_frames(16, build))
    kicks = [e for e in events if e.event_type == "kick"]
    assert len(kicks) == 1, f"esperaba 1 kick, hubo {len(kicks)}: {events}"
    print(f"  kick OK: t={kicks[0].t_start:.2f}s, vel={kicks[0].meta['ball_speed']} H/s")


def test_quiet_scene_has_no_events():
    """Jugadores dispersos y quietos → ningún evento."""
    def build(i, t, f):
        f.players.extend(background_players())
        f.players.append(player(20, 500, 200))
        f.players.append(player(21, 800, 450))

    events = extract_events(make_frames(30, build))
    assert events == [], f"escena tranquila generó eventos: {events}"
    print("  escena tranquila OK: 0 eventos")


if __name__ == "__main__":
    print("Tests de heurísticas de eventos:")
    test_ruck()
    test_tackle()
    test_carry()
    test_kick()
    test_quiet_scene_has_no_events()
    print("Todos los tests pasaron OK")
