"""Unit tests for the MJPEG stream parser and the latest-frame relay (no device)."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from openmob.device import DeviceError
from openmob.ios import MjpegParser
from openmob.server import relay_latest_frames

# --- MjpegParser -------------------------------------------------------------------


def jpeg(payload: bytes) -> bytes:
    """A fake JPEG body: SOI marker + payload."""
    return b"\xff\xd8\xff\xe0" + payload


def part(body: bytes) -> bytes:
    """One WDA-style multipart part (boundary line + headers + body + trailing CRLFs)."""
    return (
        b"--BoundaryString\r\n"
        b"Content-type: image/jpeg\r\n"
        b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body + b"\r\n\r\n"
    )


FRAMES = [jpeg(b"one"), jpeg(b"two" * 100), jpeg(b"three")]
STREAM = b"".join(part(frame) for frame in FRAMES)


def feed_in_chunks(parser: MjpegParser, data: bytes, size: int) -> list[bytes]:
    out: list[bytes] = []
    for i in range(0, len(data), size):
        out.extend(parser.feed(data[i : i + size]))
    return out


def test_parses_whole_stream_in_one_chunk() -> None:
    assert MjpegParser().feed(STREAM) == FRAMES


@pytest.mark.parametrize("size", [1, 2, 3, 7, 16, 64, 1024])
def test_parses_stream_split_at_any_chunk_size(size: int) -> None:
    assert feed_in_chunks(MjpegParser(), STREAM, size) == FRAMES


def test_skips_http_preamble_junk() -> None:
    preamble = (
        b"HTTP/1.0 200 OK\r\n"
        b"Server: WDA MJPEG Server\r\n"
        b"Content-Type: multipart/x-mixed-replace; boundary=--BoundaryString\r\n\r\n"
    )
    assert feed_in_chunks(MjpegParser(), preamble + STREAM, 5) == FRAMES


def test_huge_frame_across_many_chunks() -> None:
    huge = jpeg(b"\x00" * (2 * 1024 * 1024))
    frames = feed_in_chunks(MjpegParser(), part(huge) + part(FRAMES[0]), 64 * 1024)
    assert frames == [huge, FRAMES[0]]


def test_rejects_absurd_content_length() -> None:
    header = b"--BoundaryString\r\nContent-Length: 999999999999\r\n\r\n"
    with pytest.raises(DeviceError, match="too large"):
        MjpegParser().feed(header)


def test_drops_non_jpeg_body_and_resyncs() -> None:
    bad = b"not a jpeg at all"
    stream = part(bad) + part(FRAMES[0])
    assert MjpegParser().feed(stream) == [FRAMES[0]]


def test_body_containing_crlfcrlf_is_not_split() -> None:
    tricky = jpeg(b"aa\r\n\r\nbb\r\n\r\n--BoundaryString\r\ncc")
    assert feed_in_chunks(MjpegParser(), part(tricky) + part(FRAMES[0]), 3) == [tricky, FRAMES[0]]


def test_headerless_garbage_does_not_grow_buffer_unbounded() -> None:
    parser = MjpegParser()
    for _ in range(100):
        assert parser.feed(b"\xff" * 4096) == []
    assert len(parser._buf) <= parser.MAX_HEADER_BLOCK + 4096
    # And the parser still recovers once real parts arrive (terminator resets state).
    assert parser.feed(b"\r\n\r\n" + STREAM) == FRAMES


def test_incomplete_tail_yields_nothing_until_completed() -> None:
    data = part(FRAMES[0])
    parser = MjpegParser()
    assert parser.feed(data[:-20]) == []
    head = part(FRAMES[1])
    assert parser.feed(data[-20:] + head[: len(head) // 2]) == [FRAMES[0]]
    assert parser.feed(head[len(head) // 2 :]) == [FRAMES[1]]


# --- relay_latest_frames -----------------------------------------------------------


async def iter_frames(frames: list[bytes], delay: float = 0.0) -> AsyncIterator[bytes]:
    for frame in frames:
        yield frame
        if delay:
            await asyncio.sleep(delay)
        else:
            await asyncio.sleep(0)


def test_relay_drops_stale_frames_when_consumer_is_slow() -> None:
    produced = [b"frame-%03d" % i for i in range(50)]
    received: list[bytes] = []

    async def slow_send(frame: bytes) -> None:
        received.append(frame)
        await asyncio.sleep(0.02)

    asyncio.run(relay_latest_frames(iter_frames(produced), slow_send, max_fps=1000))
    assert received[-1] == produced[-1]  # newest frame always gets through
    assert len(received) < len(produced)  # stale frames were dropped, no backlog
    assert received == sorted(received)  # never re-sends an older frame


def test_relay_caps_fps() -> None:
    received: list[bytes] = []
    elapsed = 0.0

    async def send(frame: bytes) -> None:
        received.append(frame)

    async def run() -> None:
        # ~0.3s of frames at ~200/s against a 20fps cap.
        nonlocal elapsed
        frames = [b"f%d" % i for i in range(60)]
        loop = asyncio.get_running_loop()
        started = loop.time()
        await relay_latest_frames(iter_frames(frames, delay=0.005), send, max_fps=20)
        elapsed = loop.time() - started

    asyncio.run(run())
    assert 2 <= len(received) <= elapsed * 20 + 2  # never faster than the cap
    assert len(received) < 60  # and never one send per produced frame


def test_relay_reraises_producer_error() -> None:
    async def broken() -> AsyncIterator[bytes]:
        yield b"frame-0"
        raise DeviceError("stream died")

    received: list[bytes] = []

    async def send(frame: bytes) -> None:
        received.append(frame)

    with pytest.raises(DeviceError, match="stream died"):
        asyncio.run(relay_latest_frames(broken(), send, max_fps=1000))
    assert received == [b"frame-0"]


def test_relay_returns_when_stream_ends() -> None:
    received: list[bytes] = []

    async def send(frame: bytes) -> None:
        received.append(frame)

    asyncio.run(relay_latest_frames(iter_frames([b"a", b"b"], delay=0.01), send, max_fps=1000))
    assert received and received[-1] == b"b"


def test_relay_stops_pump_when_send_fails() -> None:
    sent = 0

    async def failing_send(frame: bytes) -> None:
        nonlocal sent
        sent += 1
        raise ConnectionError("client went away")

    async def endless() -> AsyncIterator[bytes]:
        i = 0
        while True:
            yield b"f%d" % i
            i += 1
            await asyncio.sleep(0)

    with pytest.raises(ConnectionError):
        asyncio.run(relay_latest_frames(endless(), failing_send, max_fps=1000))
    assert sent == 1
