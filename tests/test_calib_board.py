import pytest
from econ_cam.calib_board import parse_board_config, adjacent_pairs, BoardConfig, object_points


def test_checkerboard_expected_corners():
    cfg = parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25})
    assert cfg.expected_corners == 54
    assert cfg.marker_mm == 0.0


def test_charuco_requires_valid_marker_and_dict():
    cfg = parse_board_config({"board_type": "charuco", "cols": 5, "rows": 7,
                              "square_mm": 30, "marker_mm": 22, "dictionary": "DICT_5X5_100"})
    assert cfg.expected_corners == (5 - 1) * (7 - 1)  # inner chessboard corners
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "charuco", "cols": 5, "rows": 7,
                            "square_mm": 30, "marker_mm": 30})   # marker not < square


def test_invalid_inputs():
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "nope", "cols": 9, "rows": 6, "square_mm": 25})
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "checkerboard", "cols": 1, "rows": 6, "square_mm": 25})
    with pytest.raises(ValueError):
        parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 0})


def test_adjacent_pairs_array_and_ring():
    assert adjacent_pairs([0, 1, 2, 3]) == [(0, 1), (1, 2), (2, 3)]
    assert adjacent_pairs([3, 0, 2, 1], ring=True) == [(0, 1), (1, 2), (2, 3), (0, 3)]
    assert adjacent_pairs([0, 1], ring=True) == [(0, 1)]   # no wrap for a single pair


def test_to_dict_roundtrip():
    cfg = parse_board_config({"board_type": "checkerboard", "cols": 9, "rows": 6, "square_mm": 25})
    d = cfg.to_dict()
    assert parse_board_config(d).expected_corners == 54


def test_object_points_checkerboard_grid():
    cfg = BoardConfig(board_type="checkerboard", cols=3, rows=2, square_mm=25.0)
    pts = object_points(cfg)
    # 3열 x 2행 = 6개, 행 우선 순서
    assert pts == [
        (0.0, 0.0, 0.0), (25.0, 0.0, 0.0), (50.0, 0.0, 0.0),
        (0.0, 25.0, 0.0), (25.0, 25.0, 0.0), (50.0, 25.0, 0.0),
    ]


def test_object_points_count_matches_expected_corners():
    cfg = BoardConfig(board_type="checkerboard", cols=10, rows=7, square_mm=20.0)
    assert len(object_points(cfg)) == cfg.expected_corners  # 70
