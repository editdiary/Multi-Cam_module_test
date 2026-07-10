"""Checkerboard/ChArUco board configuration + camera-pair topology. Pure, no cv2."""
from dataclasses import dataclass, asdict

DICTS = ["DICT_4X4_50", "DICT_5X5_100", "DICT_6X6_250", "DICT_7X7_1000"]


@dataclass
class BoardConfig:
    board_type: str          # "checkerboard" | "charuco"
    cols: int                # checkerboard: inner corners per row; charuco: squares in X
    rows: int                # checkerboard: inner corners per col; charuco: squares in Y
    square_mm: float         # physical square size (mm)
    marker_mm: float = 0.0   # charuco only: ArUco marker size (mm)
    dictionary: str = "DICT_5X5_100"   # charuco only

    @property
    def expected_corners(self) -> int:
        if self.board_type == "checkerboard":
            return self.cols * self.rows
        return (self.cols - 1) * (self.rows - 1)   # charuco inner chessboard corners

    def to_dict(self) -> dict:
        return asdict(self)


def parse_board_config(d: dict) -> BoardConfig:
    bt = d.get("board_type", "checkerboard")
    if bt not in ("checkerboard", "charuco"):
        raise ValueError(f"unknown board_type: {bt}")
    cols, rows = int(d["cols"]), int(d["rows"])
    if cols < 2 or rows < 2:
        raise ValueError("cols/rows must be >= 2")
    square_mm = float(d["square_mm"])
    if square_mm <= 0:
        raise ValueError("square_mm must be > 0")
    cfg = BoardConfig(bt, cols, rows, square_mm)
    if bt == "charuco":
        cfg.marker_mm = float(d.get("marker_mm", 0))
        if not (0 < cfg.marker_mm < square_mm):
            raise ValueError("marker_mm must be > 0 and < square_mm")
        cfg.dictionary = d.get("dictionary", "DICT_5X5_100")
        if cfg.dictionary not in DICTS:
            raise ValueError(f"unknown dictionary: {cfg.dictionary}")
    return cfg


def object_points(cfg: BoardConfig) -> list[tuple[float, float, float]]:
    """체커보드 내부 코너의 3D 좌표(z=0). findChessboardCornersSB((cols,rows)) 순서와 동일:
    각 행마다 cols개, 총 rows개 행(행 우선)."""
    s = cfg.square_mm
    return [
        (col * s, row * s, 0.0)
        for row in range(cfg.rows)
        for col in range(cfg.cols)
    ]


def adjacent_pairs(devs: list, ring: bool = False) -> list:
    """Overlapping camera pairs. Linear array: (0,1),(1,2),... Ring adds (first,last)."""
    s = sorted(devs)
    pairs = [(s[i], s[i + 1]) for i in range(len(s) - 1)]
    if ring and len(s) > 2:
        pairs.append((s[0], s[-1]))
    return pairs
