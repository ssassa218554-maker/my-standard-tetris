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

    # IMPORTANT: initialize only once per session (protect on reruns)
    if "game_board" not in ss:
        ss.game_board = new_empty_board()
        ss.bag = refill_bag()
        ss.current_piece = next_piece()
        ss.score = 0
        ss.lines = 0
        ss.level = 1
        ss.game_over = False
        ss.paused = False
        ss.last_fall_ts = time.time()


def reset_game() -> None:
    ss = st.session_state
    ss.game_board = new_empty_board()
    ss.bag = refill_bag()
    ss.current_piece = next_piece()
    ss.score = 0
    ss.lines = 0
    ss.level = 1
    ss.game_over = False
    ss.paused = False
    ss.last_fall_ts = time.time()


def try_move(dx: int, dy: int) -> bool:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.current_piece is None:
        return False
    p = ss.current_piece
    cand = Piece(kind=p.kind, x=p.x + dx, y=p.y + dy, rot=p.rot)
    if not collides(ss.game_board, cand):
        ss.current_piece = cand
        return True
    return False


def try_rotate() -> bool:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.current_piece is None:
        return False
    p = ss.current_piece
    cand = Piece(kind=p.kind, x=p.x, y=p.y, rot=(p.rot + 1) % 4)
    if not collides(ss.game_board, cand):
        ss.current_piece = cand
        return True

    for (dx, dy) in [(-1, 0), (1, 0), (-2, 0), (2, 0), (0, -1), (-1, -1), (1, -1)]:
        kicked = Piece(kind=p.kind, x=p.x + dx, y=p.y + dy, rot=cand.rot)
        if not collides(ss.game_board, kicked):
            ss.current_piece = kicked
            return True
    return False


def hard_drop() -> None:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.current_piece is None:
        return
    dropped = 0
    while try_move(0, 1):
        dropped += 1
    if dropped:
        ss.score += dropped * 2
    step_lock_and_spawn()


def step_lock_and_spawn() -> None:
    ss = st.session_state
    if ss.current_piece is None:
        return

    lock_piece(ss.game_board, ss.current_piece)
    cleared = clear_lines(ss.game_board)
    if cleared:
        ss.lines += cleared
        ss.level = 1 + ss.lines // 10
        ss.score += score_for_lines(cleared, ss.level)

    ss.current_piece = next_piece()
    ss.last_fall_ts = time.time()
    if collides(ss.game_board, ss.current_piece):
        ss.game_over = True


def tick_fall(now: float) -> None:
    ss = st.session_state
    if ss.game_over or ss.paused or ss.current_piece is None:
        return
    interval = fall_interval_seconds(ss.level)
    if now - ss.last_fall_ts >= interval:
        if not try_move(0, 1):
            step_lock_and_spawn()
        ss.last_fall_ts = now


def merged_board() -> List[List[str]]:
    ss = st.session_state
    b = [row[:] for row in ss.game_board]
    p = ss.current_piece
    if p is None:
        return b
    for (x, y) in p.abs_cells():
        if 0 <= y < BOARD_H and 0 <= x < BOARD_W:
            b[y][x] = p.kind
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


def app_css() -> None:
    # Make the 3-zone controls huge and faint.
    st.markdown(
        """
        <style>
          .block-container { padding-top: 1.0rem; padding-bottom: 1.0rem; }

          /* Default buttons (pause/restart/drop) */
          div[data-testid="stButton"] > button {
            min-height: 48px;
            border-radius: 14px;
            font-weight: 700;
          }

          /* Big touch-zone buttons */
          .tz div[data-testid="stButton"] > button {
            min-height: 26vh;
            font-size: 18px;
            border-radius: 16px;
            background: rgba(255,255,255,0.04) !important;
            border: 1px solid rgba(255,255,255,0.10) !important;
            color: rgba(255,255,255,0.35) !important;
          }
          .tz div[data-testid="stButton"] > button:active {
            background: rgba(255,255,255,0.09) !important;
            border-color: rgba(255,255,255,0.18) !important;
            color: rgba(255,255,255,0.55) !important;
          }
          @media (prefers-color-scheme: light) {
            .tz div[data-testid="stButton"] > button {
              background: rgba(0,0,0,0.035) !important;
              border: 1px solid rgba(0,0,0,0.10) !important;
              color: rgba(0,0,0,0.35) !important;
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_touch_zones() -> None:
    ss = st.session_state
    disabled = ss.game_over or ss.paused

    cols = st.columns([3, 4, 3], gap="small")
    with cols[0]:
        st.markdown("<div class='tz'>", unsafe_allow_html=True)
        if st.button("왼쪽", key="tz_left", use_container_width=True, disabled=disabled):
            try_move(-1, 0)
        st.markdown("</div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown("<div class='tz'>", unsafe_allow_html=True)
        if st.button("회전", key="tz_rot", use_container_width=True, disabled=disabled):
            try_rotate()
        st.markdown("</div>", unsafe_allow_html=True)
    with cols[2]:
        st.markdown("<div class='tz'>", unsafe_allow_html=True)
        if st.button("오른쪽", key="tz_right", use_container_width=True, disabled=disabled):
            try_move(1, 0)
        st.markdown("</div>", unsafe_allow_html=True)


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

    tick_fall(time.time())

    top = st.columns([1, 1, 1])
    with top[0]:
        st.metric("점수", ss.score)
    with top[1]:
        st.metric("레벨", ss.level)
    with top[2]:
        st.metric("라인", ss.lines)

    # Controls: scoreboard 바로 아래 + 게임판 위
    render_touch_zones()

    # Gap between controls and board (avoid mis-taps)
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
            - **3구역 터치**: 왼쪽=좌이동 / 가운데=회전 / 오른쪽=우이동  
            - **일시정지 상태**에서는 조작이 잠깁니다.  
            - **라인 삭제**: 가득 찬 줄은 자동 삭제  
            - **레벨**: 10라인마다 +1 (낙하 속도 증가)
            """
        )


if __name__ == "__main__":
    main()

