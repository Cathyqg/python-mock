#!/usr/bin/env python3
"""Random mouse and keyboard input exerciser.

This script is intended for manual UI smoke tests. It randomly moves the
mouse inside the visible virtual screen and randomly presses Alt/CapsLock.

Safety defaults:
- Starts in dry-run mode unless --live is supplied.
- Runs for a bounded duration.
- Keeps generated coordinates inside the virtual screen.
- Avoids and treats physical screen corners as an abort area.
- Restores the original CapsLock state before exiting.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import random
import signal
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Protocol


VK_MENU = 0x12
VK_CAPITAL = 0x14
KEYEVENTF_KEYUP = 0x0002

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


class InputBackend(Protocol):
    def screen_bounds(self) -> "Bounds":
        ...

    def cursor_position(self) -> tuple[int, int]:
        ...

    def move_mouse(self, x: int, y: int) -> None:
        ...

    def press_alt(self) -> None:
        ...

    def release_alt(self) -> None:
        ...

    def press_caps_lock(self) -> None:
        ...

    def is_caps_lock_on(self) -> bool | None:
        ...


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width - 1

    @property
    def bottom(self) -> int:
        return self.top + self.height - 1

    def clamp(self, x: int, y: int, margin: int) -> tuple[int, int]:
        safe_margin_x = min(max(margin, 0), max((self.width - 1) // 2, 0))
        safe_margin_y = min(max(margin, 0), max((self.height - 1) // 2, 0))
        min_x = self.left + safe_margin_x
        max_x = self.right - safe_margin_x
        min_y = self.top + safe_margin_y
        max_y = self.bottom - safe_margin_y
        return min(max(x, min_x), max_x), min(max(y, min_y), max_y)

    def random_point(self, margin: int, rng: random.Random) -> tuple[int, int]:
        x, y = self.clamp(self.left, self.top, margin)
        max_x, max_y = self.clamp(self.right, self.bottom, margin)
        return rng.randint(x, max_x), rng.randint(y, max_y)

    def corners(self) -> Iterable[tuple[int, int]]:
        yield self.left, self.top
        yield self.right, self.top
        yield self.left, self.bottom
        yield self.right, self.bottom


class WindowsBackend:
    """Windows input backend using only the standard library."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsBackend is only available on Windows.")
        self.user32 = ctypes.windll.user32

    def screen_bounds(self) -> Bounds:
        left = self.user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        top = self.user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        width = self.user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        height = self.user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid virtual screen size: {width}x{height}.")
        return Bounds(left=left, top=top, width=width, height=height)

    def cursor_position(self) -> tuple[int, int]:
        point = ctypes.wintypes.POINT()
        if not self.user32.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError()
        return int(point.x), int(point.y)

    def move_mouse(self, x: int, y: int) -> None:
        if not self.user32.SetCursorPos(int(x), int(y)):
            raise ctypes.WinError()

    def press_alt(self) -> None:
        self.user32.keybd_event(VK_MENU, 0, 0, 0)
        self.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    def release_alt(self) -> None:
        self.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)

    def press_caps_lock(self) -> None:
        self.user32.keybd_event(VK_CAPITAL, 0, 0, 0)
        self.user32.keybd_event(VK_CAPITAL, 0, KEYEVENTF_KEYUP, 0)

    def is_caps_lock_on(self) -> bool:
        return bool(self.user32.GetKeyState(VK_CAPITAL) & 1)


class PyAutoGuiBackend:
    """Fallback backend for non-Windows platforms when pyautogui is installed."""

    def __init__(self) -> None:
        try:
            import pyautogui  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "pyautogui is required on non-Windows platforms. "
                "Install it with: python -m pip install pyautogui"
            ) from exc
        pyautogui.FAILSAFE = False
        self.pyautogui = pyautogui

    def screen_bounds(self) -> Bounds:
        width, height = self.pyautogui.size()
        if width <= 0 or height <= 0:
            raise RuntimeError(f"Invalid screen size: {width}x{height}.")
        return Bounds(left=0, top=0, width=int(width), height=int(height))

    def cursor_position(self) -> tuple[int, int]:
        position = self.pyautogui.position()
        return int(position.x), int(position.y)

    def move_mouse(self, x: int, y: int) -> None:
        self.pyautogui.moveTo(int(x), int(y), duration=0)

    def press_alt(self) -> None:
        self.pyautogui.press("alt")

    def release_alt(self) -> None:
        self.pyautogui.keyUp("alt")

    def press_caps_lock(self) -> None:
        self.pyautogui.press("capslock")

    def is_caps_lock_on(self) -> bool | None:
        return None


class DryRunBackend:
    def __init__(self, backend: InputBackend | None = None) -> None:
        self.backend = backend
        self._bounds: Bounds | None = None
        self._cursor: tuple[int, int] | None = None

    def screen_bounds(self) -> Bounds:
        if self.backend is None:
            self._bounds = Bounds(left=0, top=0, width=1920, height=1080)
        else:
            self._bounds = self.backend.screen_bounds()
        self._cursor = (
            self._bounds.left + self._bounds.width // 2,
            self._bounds.top + self._bounds.height // 2,
        )
        return self._bounds

    def cursor_position(self) -> tuple[int, int]:
        if self._cursor is not None:
            return self._cursor
        bounds = self.screen_bounds()
        return bounds.left + bounds.width // 2, bounds.top + bounds.height // 2

    def move_mouse(self, x: int, y: int) -> None:
        self._cursor = (x, y)
        print(f"[dry-run] move mouse to ({x}, {y})")

    def press_alt(self) -> None:
        print("[dry-run] press Alt")

    def release_alt(self) -> None:
        print("[dry-run] release Alt")

    def press_caps_lock(self) -> None:
        print("[dry-run] press CapsLock")

    def is_caps_lock_on(self) -> bool | None:
        return None


def build_backend(dry_run: bool) -> InputBackend:
    real_backend: InputBackend | None = None
    try:
        real_backend = WindowsBackend() if sys.platform == "win32" else PyAutoGuiBackend()
    except Exception as exc:
        if not dry_run:
            raise
        print(f"[dry-run] using fallback 1920x1080 bounds because backend failed: {exc}")

    if dry_run:
        return DryRunBackend(real_backend)
    if real_backend is None:
        raise RuntimeError("No usable input backend found.")
    return real_backend


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return parsed


def probability(value: str) -> float:
    parsed = float(value)
    if not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("probability must be between 0 and 1")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Randomly move the mouse and press Alt/CapsLock for UI testing."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually send input events. Without this flag the script only prints actions.",
    )
    parser.add_argument("--duration", type=positive_float, default=15.0, help="Max seconds to run.")
    parser.add_argument("--max-actions", type=int, default=50, help="Max actions to perform.")
    parser.add_argument("--min-delay", type=positive_float, default=0.15, help="Min delay between actions.")
    parser.add_argument("--max-delay", type=positive_float, default=0.8, help="Max delay between actions.")
    parser.add_argument("--margin", type=int, default=16, help="Pixels to keep away from screen edges.")
    parser.add_argument(
        "--corner-abort-margin",
        type=int,
        default=10,
        help="Abort if the physical cursor is this close to any screen corner. Use 0 to disable.",
    )
    parser.add_argument("--mouse-prob", type=probability, default=0.70, help="Chance of mouse move per action.")
    parser.add_argument("--alt-prob", type=probability, default=0.20, help="Chance of Alt press per action.")
    parser.add_argument("--caps-prob", type=probability, default=0.10, help="Chance of CapsLock press per action.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for repeatable tests.")
    parser.add_argument("--countdown", type=positive_float, default=3.0, help="Seconds before live actions start.")
    parser.add_argument(
        "--restore-caps-lock",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Restore original CapsLock state before exiting when the backend can detect it.",
    )
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.max_actions <= 0:
        raise ValueError("--max-actions must be > 0.")
    if args.min_delay > args.max_delay:
        raise ValueError("--min-delay cannot be greater than --max-delay.")
    if args.mouse_prob + args.alt_prob + args.caps_prob <= 0:
        raise ValueError("At least one action probability must be greater than 0.")
    if args.margin < 0:
        raise ValueError("--margin must be >= 0.")
    if args.corner_abort_margin < 0:
        raise ValueError("--corner-abort-margin must be >= 0.")


def normalize_weights(args: argparse.Namespace) -> tuple[float, float, float]:
    total = args.mouse_prob + args.alt_prob + args.caps_prob
    return args.mouse_prob / total, args.alt_prob / total, args.caps_prob / total


def is_near_corner(x: int, y: int, bounds: Bounds, margin: int) -> bool:
    if margin <= 0:
        return False
    return any(abs(x - cx) <= margin and abs(y - cy) <= margin for cx, cy in bounds.corners())


def pick_action(rng: random.Random, weights: tuple[float, float, float]) -> str:
    value = rng.random()
    mouse_weight, alt_weight, _caps_weight = weights
    if value < mouse_weight:
        return "mouse"
    if value < mouse_weight + alt_weight:
        return "alt"
    return "caps"


def countdown(seconds: float, live: bool) -> None:
    if not live or seconds <= 0:
        return
    print(f"Starting live input in {seconds:.1f}s. Move cursor to a screen corner or press Ctrl+C to stop.")
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        print(f"  {remaining:.1f}s", end="\r", flush=True)
        time.sleep(min(0.25, remaining))
    print(" " * 32, end="\r")


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    rng = random.Random(args.seed)
    backend = build_backend(dry_run=not args.live)
    bounds = backend.screen_bounds()
    weights = normalize_weights(args)
    original_caps = backend.is_caps_lock_on()
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_sigint = signal.signal(signal.SIGINT, request_stop)

    print(
        f"bounds=({bounds.left},{bounds.top})..({bounds.right},{bounds.bottom}) "
        f"size={bounds.width}x{bounds.height} mode={'live' if args.live else 'dry-run'}"
    )

    actions_done = 0

    try:
        countdown(args.countdown, args.live)
        started = time.monotonic()
        while actions_done < args.max_actions and time.monotonic() - started < args.duration:
            current_x, current_y = backend.cursor_position()
            if is_near_corner(current_x, current_y, bounds, args.corner_abort_margin):
                print(f"abort: cursor is near a screen corner at ({current_x}, {current_y}).")
                break

            action = pick_action(rng, weights)
            if action == "mouse":
                x, y = bounds.random_point(args.margin, rng)
                x, y = bounds.clamp(x, y, args.margin)
                backend.move_mouse(x, y)
            elif action == "alt":
                backend.press_alt()
            else:
                backend.press_caps_lock()

            actions_done += 1
            time.sleep(rng.uniform(args.min_delay, args.max_delay))

            if stop_requested:
                print("stop requested by Ctrl+C.")
                break
    finally:
        backend.release_alt()
        if args.restore_caps_lock and original_caps is not None:
            current_caps = backend.is_caps_lock_on()
            if current_caps is not None and current_caps != original_caps:
                backend.press_caps_lock()
                print("restored original CapsLock state.")
        signal.signal(signal.SIGINT, previous_sigint)

    print(f"completed actions={actions_done}")
    return 0


def main() -> int:
    try:
        return run(parse_args())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
