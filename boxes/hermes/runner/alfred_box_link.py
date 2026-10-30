"""The line between the box runner and ALFRED, shared by the runner and its tool gate plugin.

Runs inside the sealed Hermes box only (docs/HERMES_BOX.md). ALFRED is reached through the
runner's own standard input and output, one JSON object per line. Hermes's own printing is
moved to standard error before Hermes is imported, so nothing Hermes writes can be read as a
frame. Standard library only.
"""
from __future__ import annotations
import itertools
import json
import os
import queue
import threading

PROTOCOL = 1
MAX_FRAME = 8 * 1024 * 1024
REPLY_SECONDS = 600


class LinkClosed(Exception):
    pass


class Link:
    """Frames out on one file descriptor, replies in on another, matched by id.

    Hermes may call tools on several threads and its model client may retry, so any thread
    may ask; one reader thread hands each reply to the thread waiting for it.
    """

    def __init__(self, read_fd: int, write_fd: int):
        self._reader = os.fdopen(read_fd, 'rb')
        self._write_fd = write_fd
        self._write_lock = threading.Lock()
        self._waiting: dict[int, queue.Queue] = {}
        self._waiting_lock = threading.Lock()
        self._ids = itertools.count(1)
        self.closed = threading.Event()

    def send(self, frame: dict) -> None:
        data = json.dumps(frame, separators=(',', ':'), ensure_ascii=True).encode('ascii') + b'\n'
        if len(data) > MAX_FRAME:
            raise ValueError('frame_too_large')
        with self._write_lock:
            view = memoryview(data)
            while view:
                written = os.write(self._write_fd, view)
                view = view[written:]

    def read(self) -> dict:
        line = self._reader.readline(MAX_FRAME + 1)
        if not line.endswith(b'\n'):
            raise ValueError('frame_too_large') if len(line) > MAX_FRAME else LinkClosed('eof')
        frame = json.loads(line)
        if not isinstance(frame, dict) or not isinstance(frame.get('type'), str):
            raise ValueError('bad_frame')
        return frame

    def start_replies(self) -> None:
        threading.Thread(target=self._replies, name='alfred-link', daemon=True).start()

    def _replies(self) -> None:
        try:
            while True:
                frame = self.read()
                with self._waiting_lock:
                    waiter = self._waiting.pop(frame.get('id'), None)
                if waiter is not None:
                    waiter.put(frame)
        except Exception:
            pass
        self.closed.set()
        with self._waiting_lock:
            waiters, self._waiting = list(self._waiting.values()), {}
        for waiter in waiters:
            waiter.put(None)

    def ask(self, frame: dict) -> dict:
        """Send a request and wait for ALFRED's reply to it. Raises LinkClosed when ALFRED
        has gone, so a caller that cannot get an answer refuses rather than carries on."""
        if self.closed.is_set():
            raise LinkClosed('closed')
        number = next(self._ids)
        waiter: queue.Queue = queue.Queue(maxsize=1)
        with self._waiting_lock:
            self._waiting[number] = waiter
        self.send({**frame, 'id': number})
        try:
            reply = waiter.get(timeout=REPLY_SECONDS)
        except queue.Empty:
            raise LinkClosed('no_reply') from None
        if reply is None:
            raise LinkClosed('closed')
        return reply


LINK: Link | None = None


def check_tool(tool: str, args) -> dict:
    """Ask ALFRED whether this one tool call may run. Anything but an explicit yes is a no."""
    if LINK is None:
        return {'allow': False, 'message': 'ALFRED is not connected.'}
    try:
        safe_args = json.loads(json.dumps(args if isinstance(args, dict) else {}, default=str))
        reply = LINK.ask({'type': 'tool_check', 'tool': str(tool)[:80], 'args': safe_args})
    except Exception:
        return {'allow': False, 'message': 'ALFRED could not be asked, so the tool was refused.'}
    if reply.get('type') != 'tool_decision' or reply.get('allow') is not True:
        message = reply.get('message') if isinstance(reply.get('message'), str) else ''
        return {'allow': False, 'message': message or 'ALFRED refused this tool.'}
    return {'allow': True}
