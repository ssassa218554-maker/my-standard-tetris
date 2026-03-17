import random
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import streamlit as st

try:
    # pip install streamlit-autorefresh
    from streamlit_autorefresh import st_autorefresh
except Exception:  # pragma: no cover
    st_autorefresh = None


BOARD_W = 10
BOARD_H = 20

# Standard guideline-ish colors (web-friendly)
COLORS: Dict[str, str] = {
    "I": "#00F0F0",  # cyan
    "J": "#0000F0",  # blue
    "L": "#F0A000",  # orange
    "O": "#F0F000",  # yellow
    "S": "#00F000",  # green
    "T": "#A000F0",  # purple
    "Z": "#F00000",  # red
    "": "#00000000",  # empty (transparent)
}


def rotate_cw(cells: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    # (x, y) -> (y, -x)
    return [(y, -x) for (x, y) in cells]


# Tetrominoes defined by relative 4 blocks (x, y) around an origin (0,0)
SHAPES: Dict[str, List[Tuple[int, int]]] = {
    "I": [(-1, 0), (0, 0), (1, 0), (2, 0)],
    "J": [(-1, 0), (0, 0), (1, 0), (1, 1)],
    "L": [(-1, 0), (0, 0), (1, 0), (-1, 1)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "S": [(-1, 1), (0, 1), (0, 0), (1, 0)],
    "T": [(-1, 0), (0, 0), (1, 0), (0, 1)],
    "Z": [(-1, 0), (0, 0), (0, 1), (1, 1)],
}


@dataclass
class Piece:
    kind: str
    x: int
    y: int
    rot: int = 0

    def cells(self) -> List[Tuple[int, int]]:
        cells = SHAPES[self.kind]
        if self.kind == "O":
            return cells
        out = list(cells)
        for _ in range(self.rot % 4):
            out = rotate_cw(out)
        return out

    def abs_cells(self) -> List[Tuple[int, int]]:
        return [(self.x + cx, self.y + cy) for (cx, cy) in self.cells()]


def new_empty_board() -> List[List[str]]:
    return [["" for _ in range(BOARD_W)] for _ in range(BOARD_H)]


def collides(board: List[List[str]], piece: Piece) -> bool:
    for (x, y) in piece.abs_cells():
        if x < 0 or x >= BOARD_W or y >= BOARD_H:
            return True
        if y >= 0 and board[y][x] != "":
            return True
    return False


def lock_piece(board: List[List[str]], piece: Piece) -> None:
    for (x, y) in piece.abs_cells():
        if 0 <= y < BOARD_H and 0 <= x < BOARD_W:
            board[y][x] = piece.kind


def clear_lines(board: List[List[str]]) -> int:
    new_rows = [row for row in board if any(cell == "" for cell in row)]
    cleared = BOARD_H - len(new_rows)
    for _ in range(cleared):
        new_rows.insert(0, ["" for _ in range(BOARD_W)])
    board[:] = new_rows
    return cleared


def score_for_lines(n: int, level: int) -> int:
    base = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}[n]
    return base * max(1, level)


def fall_interval_seconds(level: int) -> float:
    return max(0.08, 0.8 - 0.06 * (level - 1))


def spawn_piece(kind: str) -> Piece:
    return Piece(kind=kind, x=BOARD_W // 2 - 1, y=-1, rot=0)


def refill_bag() -> List[str]:
    bag = list(SHAPES.keys())
    random.shuffle(bag)
    return bag


def next_piece() -> Piece:
    ss = st.session_state
    if not ss.bag:
        ss.bag = refill_bag()
    kind = ss.bag.pop()
    return spawn_piece(kind)


def ensure_state() -> None:
    ss = st.session_state
    if "board" not in ss:
        ss.board = new_empty_board()
    if "bag" not in ss:
        ss.bag = refill_bag()
    if "piece" not in ss:
        ss.piece = None
    if "score" not in ss:
        ss.score = 0
    if "lines" not in ss:
        ss.lines = 0
    if "level" not in ss:
        ss.level = 1
    if "game_over" not in ss:
        ss.game_over = False
    if "paused" not in ss:
        ss.paused = False
    if "last_fall_ts" not in ss:
        ss.last_fall_ts = time.time()

    if ss.piece is None and not ss.game_over:
        ss.piece = next_piece()
        ss.last_fall_ts = time.time()


def reset_game() -> None:
    ss = st.session_state
    ss.board = new_empty_board()
    ss.bag = refill_bag()
    ss.piece = next_piece()
    ss.score = 0
    ss.lines = 0
    ss.level = 1
    ss.game_over = False
    ss.paused = False
    ss.last_fall_ts = time.time()


def try_move(dx: int, dy: int) -> bool:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.piece is None:
        return False
    p = ss.piece
    cand = Piece(kind=p.kind, x=p.x + dx, y=p.y + dy, rot=p.rot)
    if not collides(ss.board, cand):
        ss.piece = cand
        return True
    return False


def try_rotate() -> bool:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.piece is None:
        return False
    p = ss.piece
    cand = Piece(kind=p.kind, x=p.x, y=p.y, rot=(p.rot + 1) % 4)
    if not collides(ss.board, cand):
        ss.piece = cand
        return True

    # Simple wall kicks (not full SRS)
    for (dx, dy) in [(-1, 0), (1, 0), (-2, 0), (2, 0), (0, -1), (-1, -1), (1, -1)]:
        kicked = Piece(kind=p.kind, x=p.x + dx, y=p.y + dy, rot=cand.rot)
        if not collides(ss.board, kicked):
            ss.piece = kicked
            return True
    return False


def hard_drop() -> None:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.piece is None:
        return
    dropped = 0
    while try_move(0, 1):
        dropped += 1
    if dropped:
        ss.score += dropped * 2
    step_lock_and_spawn()


def step_lock_and_spawn() -> None:
    ss = st.session_state
    if ss.piece is None:
        return
    lock_piece(ss.board, ss.piece)
    cleared = clear_lines(ss.board)
    if cleared:
        ss.lines += cleared
        ss.level = 1 + ss.lines // 10
        ss.score += score_for_lines(cleared, ss.level)
    ss.piece = next_piece()
    ss.last_fall_ts = time.time()
    if collides(ss.board, ss.piece):
        ss.game_over = True


def tick_fall(now: float) -> None:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.piece is None:
        return
    interval = fall_interval_seconds(ss.level)
    if now - ss.last_fall_ts >= interval:
        if not try_move(0, 1):
            step_lock_and_spawn()
        ss.last_fall_ts = now


def merged_board() -> List[List[str]]:
    ss = st.session_state
    b = [row[:] for row in ss.board]
    if ss.piece is None:
        return b
    for (x, y) in ss.piece.abs_cells():
        if 0 <= y < BOARD_H and 0 <= x < BOARD_W:
            b[y][x] = ss.piece.kind
    return b


def render_board_html(board: List[List[str]]) -> str:
    cells_html = []
    for y in range(BOARD_H):
        for x in range(BOARD_W):
            k = board[y][x]
            color = COLORS.get(k, "#00000000")
            cells_html.append(f'<div class="cell" style="background:{color}"></div>')

    return f"""
    <style>
      .wrap {{
        display: flex;
        justify-content: center;
        width: 100%;
      }}
      .board {{
        width: min(92vw, 380px);
        aspect-ratio: {BOARD_W} / {BOARD_H};
        background: #111;
        border: 2px solid #333;
        border-radius: 10px;
        padding: 8px;
        box-sizing: border-box;
      }}
      .grid {{
        display: grid;
        width: 100%;
        height: 100%;
        grid-template-columns: repeat({BOARD_W}, 1fr);
        grid-template-rows: repeat({BOARD_H}, 1fr);
        gap: 2px;
      }}
      .cell {{
        border-radius: 3px;
        box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
      }}
      @media (prefers-color-scheme: dark) {{
        .board {{ background: #0E0E10; border-color:#2A2A2E; }}
      }}
    </style>
    <div class="wrap">
      <div class="board">
        <div class="grid">
          {''.join(cells_html)}
        </div>
      </div>
    </div>
    """


def render_touch_zones_html() -> str:
    # Big 3-zone controls placed between scoreboard and board.
    # Use links that set query params; Streamlit reruns on navigation.
    return """
    <style>
      :root{
        --tz-h: 26vh;
        --tz-bg: rgba(255,255,255,0.04);
        --tz-border: rgba(255,255,255,0.10);
        --tz-text: rgba(255,255,255,0.35);
      }
      .touchbar {
        height: var(--tz-h);
        display: flex;
        gap: 0px;
        padding: 8px 6px;
        box-sizing: border-box;
        background: transparent;
        -webkit-tap-highlight-color: transparent;
        touch-action: manipulation;
        margin: 10px 0 18px 0;
      }
      .zone {
        display: flex;
        align-items: center;
        justify-content: center;
        text-decoration: none;
        border-radius: 16px;
        border: 1px solid var(--tz-border);
        background: var(--tz-bg);
        color: var(--tz-text);
        font-size: 18px;
        font-weight: 700;
        user-select: none;
        -webkit-user-select: none;
        width: 100%;
      }
      .zone:active {
        background: rgba(255,255,255,0.09);
        border-color: rgba(255,255,255,0.18);
        color: rgba(255,255,255,0.55);
      }
      .zone.left  { flex: 3; }
      .zone.mid   { flex: 4; }
      .zone.right { flex: 3; }
      @media (prefers-color-scheme: light) {
        :root{
          --tz-bg: rgba(0,0,0,0.035);
          --tz-border: rgba(0,0,0,0.10);
          --tz-text: rgba(0,0,0,0.35);
        }
      }
    </style>

    <div class="touchbar" role="group" aria-label="tetris touch controls">
      <a class="zone left" href="?a=l" aria-label="move left">왼쪽</a>
      <a class="zone mid" href="?a=rot" aria-label="rotate">회전</a>
      <a class="zone right" href="?a=r" aria-label="move right">오른쪽</a>
    </div>
    """


def apply_query_action() -> None:
    try:
        a = st.query_params.get("a")
    except Exception:  # pragma: no cover
        a = None

    if isinstance(a, list):
        a = a[0] if a else None

    if not a:
        return

    ss = st.session_state
    if not ss.game_over and not ss.paused:
        if a == "l":
            try_move(-1, 0)
        elif a == "r":
            try_move(1, 0)
        elif a == "rot":
            try_rotate()

    # Clear params to prevent repeating action on autorefresh reruns.
    try:
        st.query_params.clear()
    except Exception:  # pragma: no cover
        pass


def app_css() -> None:
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.0rem; padding-bottom: 1.0rem; }
          div[data-testid="stButton"] > button {
            min-height: 48px;
            border-radius: 14px;
            font-weight: 700;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(page_title="Streamlit Tetris", page_icon="🧱", layout="centered")
    ensure_state()
    app_css()

    ss = st.session_state

    st.title("테트리스")

    if st_autorefresh is None:
        st.warning("자동 낙하(타이머)를 위해 `streamlit-autorefresh` 설치가 필요합니다.")
        st.code("pip install streamlit-autorefresh", language="bash")
    else:
        st_autorefresh(interval=120, key="tetris_tick")

    # Apply any tap action first (responsive feel), then gravity tick.
    apply_query_action()
    tick_fall(time.time())

    top = st.columns([1, 1, 1])
    with top[0]:
        st.metric("점수", ss.score)
    with top[1]:
        st.metric("레벨", ss.level)
    with top[2]:
        st.metric("라인", ss.lines)

    # Place controls here: 바로 아래(점수/레벨판 아래) + 게임판 위
    st.markdown(render_touch_zones_html(), unsafe_allow_html=True)

    # Extra gap between controls and board to avoid mis-taps.
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    if ss.game_over:
        st.error("게임 오버! 아래의 '재시작'을 눌러 다시 시작하세요.")
    elif ss.paused:
        st.info("일시정지 상태입니다.")

    st.markdown(render_board_html(merged_board()), unsafe_allow_html=True)

    st.divider()

    bottom = st.columns([1, 1, 1])
    with bottom[0]:
        if st.button("⏹️ 일시정지/재개", use_container_width=True, disabled=ss.game_over):
            ss.paused = not ss.paused
    with bottom[1]:
        if st.button("⏬⏬ 하드드롭", use_container_width=True, disabled=ss.game_over):
            hard_drop()
    with bottom[2]:
        if st.button("🔄 재시작", use_container_width=True):
            reset_game()

    with st.expander("조작 방법"):
        st.markdown(
            """
            - **조작 3구역 터치**: 왼쪽=좌이동 / 가운데=회전 / 오른쪽=우이동  
            - **라인 삭제**: 가득 찬 줄은 자동 삭제  
            - **레벨**: 10라인마다 +1 (낙하 속도 증가)
            """
        )


if __name__ == "__main__":
    main()

