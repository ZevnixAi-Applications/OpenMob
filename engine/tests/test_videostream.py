"""Unit tests for the video streaming helpers (no device required)."""

from openmob.videostream import JpegStreamParser, RestartGuard, capped_size


def jpeg(payload: bytes = b"data") -> bytes:
    return b"\xff\xd8" + payload + b"\xff\xd9"


class TestJpegStreamParser:
    def test_single_frame_one_chunk(self) -> None:
        parser = JpegStreamParser()
        assert parser.feed(jpeg()) == [jpeg()]

    def test_frame_split_byte_by_byte(self) -> None:
        parser = JpegStreamParser()
        frame = jpeg(b"split across many tiny chunks")
        collected = []
        for i in range(len(frame)):
            collected += parser.feed(frame[i : i + 1])
        assert collected == [frame]

    def test_soi_split_across_chunks(self) -> None:
        parser = JpegStreamParser()
        frame = jpeg(b"payload")
        assert parser.feed(b"garbage\xff") == []
        assert parser.feed(frame[1:]) == [frame]

    def test_garbage_between_frames(self) -> None:
        parser = JpegStreamParser()
        first, second = jpeg(b"one"), jpeg(b"two")
        data = b"junk" + first + b"\x00\x01noise" + second + b"tail"
        assert parser.feed(data) == [first, second]

    def test_multiple_frames_one_chunk(self) -> None:
        parser = JpegStreamParser()
        frames = [jpeg(b"a"), jpeg(b"b"), jpeg(b"c")]
        assert parser.feed(b"".join(frames)) == frames

    def test_partial_frame_completed_later(self) -> None:
        parser = JpegStreamParser()
        frame = jpeg(b"big payload")
        assert parser.feed(frame[:6]) == []
        assert parser.feed(frame[6:]) == [frame]

    def test_garbage_only_is_discarded(self) -> None:
        parser = JpegStreamParser()
        assert parser.feed(b"no markers here") == []
        assert parser.feed(jpeg()) == [jpeg()]


class TestRestartGuard:
    def test_not_exhausted_below_limit(self) -> None:
        guard = RestartGuard(max_failures=3)
        guard.record_failure()
        guard.record_failure()
        assert not guard.exhausted

    def test_exhausted_at_limit(self) -> None:
        guard = RestartGuard(max_failures=3)
        for _ in range(3):
            guard.record_failure()
        assert guard.exhausted

    def test_success_resets_failures(self) -> None:
        guard = RestartGuard(max_failures=2)
        guard.record_failure()
        guard.record_success()
        guard.record_failure()
        assert not guard.exhausted


class TestCappedSize:
    def test_downscales_to_max_width(self) -> None:
        assert capped_size(1080, 2400) == (720, 1600)

    def test_small_screen_unchanged(self) -> None:
        assert capped_size(720, 1280) == (720, 1280)

    def test_result_is_even(self) -> None:
        width, height = capped_size(1082, 2403)
        assert width % 2 == 0 and height % 2 == 0
