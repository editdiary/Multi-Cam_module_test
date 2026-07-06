"""V4L2 카메라 감지 및 컨트롤 (v4l2-ctl subprocess 래퍼 + 출력 파서)."""

import os
import re
import subprocess

_CTRL_RE = re.compile(r"^\s*(\w+)\s+0x[0-9a-fA-F]+\s+\((\w+)\)\s*:\s*(.*)$")
_INT_FIELDS = ("min", "max", "step", "default", "value")


# --- 순수 파서 -----------------------------------------------------------

def parse_card_type(info_text):
    """v4l2-ctl --info 출력에서 'Card type' 값을 추출."""
    for line in info_text.splitlines():
        if "Card type" in line:
            return line.split(":", 1)[1].strip()
    return "Unknown"


def parse_resolutions(text):
    """--list-formats-ext 출력에서 'Size: Discrete WxH'를 순서 유지·중복 제거로 추출."""
    res = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Size: Discrete"):
            wh = line.split()[-1]
            w, h = wh.split("x")
            item = (int(w), int(h))
            if item not in res:
                res.append(item)
    return res


def parse_controls(text):
    """v4l2-ctl -L 출력에서 컨트롤 목록을 파싱.

    각 컨트롤: {"type": str, "min"/"max"/"step"/"default"/"value": int(있을 때)}.
    메뉴 옵션 서브라인은 무시한다.
    """
    controls = {}
    for line in text.splitlines():
        m = _CTRL_RE.match(line)
        if not m:
            continue
        name, ctype, rest = m.group(1), m.group(2), m.group(3)
        entry = {"type": ctype}
        fields = {}
        for token in rest.split():
            if "=" in token:
                k, v = token.split("=", 1)
                fields[k] = v
        for k in _INT_FIELDS:
            if k in fields:
                try:
                    entry[k] = int(fields[k])
                except ValueError:
                    entry[k] = fields[k]
        controls[name] = entry
    return controls


# --- subprocess 래퍼 -----------------------------------------------------

def _run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=5).stdout


def detect_cameras():
    """/dev/video0..15 중 카드 이름에 'ar0234'가 포함된 캡처 노드를 반환."""
    cams = []
    for i in range(16):
        if not os.path.exists(f"/dev/video{i}"):
            continue
        card = parse_card_type(_run(["v4l2-ctl", "-d", f"/dev/video{i}", "--info"]))
        if "ar0234" in card.lower():
            cams.append({"dev": i, "name": card, "label": f"Camera {i} ({card})"})
    return cams


def list_resolutions(dev):
    return parse_resolutions(_run(["v4l2-ctl", "-d", f"/dev/video{dev}", "--list-formats-ext"]))


def get_controls(dev):
    return parse_controls(_run(["v4l2-ctl", "-d", f"/dev/video{dev}", "-L"]))


def set_control(dev, name, value):
    result = subprocess.run(
        ["v4l2-ctl", "-d", f"/dev/video{dev}", "-c", f"{name}={value}"],
        capture_output=True, text=True, timeout=5,
    )
    return result.returncode == 0


def set_frame_sync(dev, mode):
    """frame_sync 설정: 0=Disable, 1=30Hz, 2=60Hz."""
    return set_control(dev, "frame_sync", mode)
