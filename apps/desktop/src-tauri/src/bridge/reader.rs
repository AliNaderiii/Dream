//! Bounded newline-delimited frame reader for the sidecar's stdout (SEC-10).
//!
//! `tokio::io::Lines` buffers a whole line before the caller can look at its
//! size, so a runaway or hostile sidecar could force the shell to allocate an
//! arbitrarily large `String` before `framing::parse` ever rejected it. This
//! reader enforces [`MAX_FRAME_BYTES`] *while* reading:
//!
//! - a frame is accumulated at most up to the cap;
//! - once the cap is exceeded the rest of that line is consumed and dropped
//!   chunk by chunk, and a typed [`BridgeError::frame_too_large`] is returned
//!   instead of the frame — the stream stays in sync on the next line;
//! - invalid UTF-8 yields a typed error for that frame only;
//! - partial reads (a frame split across several pipe reads) and multiple
//!   frames in one read are both handled by scanning the buffered bytes;
//! - a trailing frame without `\n` at EOF is delivered (protocol §1.2).
//!
//! The reader is pure over `AsyncBufRead`, so it is unit-tested against
//! in-memory duplex pipes with no process involved.

use tokio::io::{AsyncBufRead, AsyncBufReadExt};

use crate::bridge::framing::MAX_FRAME_BYTES;
use crate::error::BridgeError;

/// One read outcome: a complete frame (without its newline and without a
/// trailing `\r`), a per-frame error, or end of stream.
#[derive(Debug)]
pub enum Frame {
    /// A complete line, ready for [`crate::bridge::framing::parse`].
    Line(String),
    /// The frame was oversized or not UTF-8; it has been skipped. The stream is
    /// positioned at the start of the next frame.
    Rejected(BridgeError),
    /// The peer closed its stdout (or the pipe broke).
    Eof,
}

/// Reads bounded frames from an `AsyncBufRead`.
///
/// Cancellation-safe: `next_frame` is polled inside a `select!`. Its only
/// await points are `fill_buf`, which consumes nothing, and the discard state
/// (`discarding`) is kept on the struct, so a future dropped mid-skip resumes
/// skipping the same over-long line instead of delivering its tail.
pub struct FrameReader<R> {
    inner: R,
    max_bytes: usize,
    buf: Vec<u8>,
    /// `Some(bytes_seen_so_far)` while the rest of an over-long line is being
    /// discarded.
    discarding: Option<usize>,
}

impl<R: AsyncBufRead + Unpin> FrameReader<R> {
    /// Wrap `inner` with the production frame bound ([`MAX_FRAME_BYTES`]).
    pub fn new(inner: R) -> Self {
        Self::with_limit(inner, MAX_FRAME_BYTES)
    }

    /// Wrap `inner` with an explicit bound (tests use small values).
    pub fn with_limit(inner: R, max_bytes: usize) -> Self {
        Self {
            inner,
            max_bytes,
            buf: Vec::new(),
            discarding: None,
        }
    }

    /// Read the next frame. Never allocates more than `max_bytes` for a
    /// single frame; I/O errors are returned as `Err` (instance death).
    pub async fn next_frame(&mut self) -> std::io::Result<Frame> {
        if let Some(counted) = self.discarding {
            // Resume a discard interrupted by cancellation.
            let total = self.skip_line(counted).await?;
            return Ok(Frame::Rejected(BridgeError::frame_too_large(
                total,
                self.max_bytes,
            )));
        }
        loop {
            let available = self.inner.fill_buf().await?;
            if available.is_empty() {
                // EOF: deliver a trailing unterminated frame, if any.
                if self.buf.is_empty() {
                    return Ok(Frame::Eof);
                }
                let frame = std::mem::take(&mut self.buf);
                return Ok(finish_frame(frame));
            }

            // `available` borrows `self.inner`; the pending frame lives in the
            // disjoint field `self.buf`, so the push is done through a free
            // function on that field only.
            match memchr(b'\n', available) {
                Some(index) => {
                    let outcome = push(&mut self.buf, self.max_bytes, &available[..index]);
                    self.inner.consume(index + 1);
                    match outcome {
                        Push::Ok => {
                            let frame = std::mem::take(&mut self.buf);
                            return Ok(finish_frame(frame));
                        }
                        Push::Oversized(total) => {
                            self.buf.clear();
                            return Ok(Frame::Rejected(BridgeError::frame_too_large(
                                total,
                                self.max_bytes,
                            )));
                        }
                    }
                }
                None => {
                    let len = available.len();
                    let outcome = push(&mut self.buf, self.max_bytes, available);
                    self.inner.consume(len);
                    if let Push::Oversized(total) = outcome {
                        // Discard the remainder of this over-long line without
                        // holding it, then report once. The partial frame is
                        // released now so nothing is retained while skipping.
                        self.buf.clear();
                        self.discarding = Some(total);
                        let total = self.skip_line(total).await?;
                        return Ok(Frame::Rejected(BridgeError::frame_too_large(
                            total,
                            self.max_bytes,
                        )));
                    }
                }
            }
        }
    }

    /// Consume bytes up to and including the next `\n` (or EOF) without
    /// storing them. Returns the running byte count for diagnostics. The
    /// progress is mirrored into `self.discarding` so a cancelled call can be
    /// resumed by the next `next_frame`.
    async fn skip_line(&mut self, mut counted: usize) -> std::io::Result<usize> {
        loop {
            let available = self.inner.fill_buf().await?;
            if available.is_empty() {
                self.discarding = None;
                return Ok(counted);
            }
            match memchr(b'\n', available) {
                Some(index) => {
                    counted = counted.saturating_add(index);
                    self.inner.consume(index + 1);
                    self.discarding = None;
                    return Ok(counted);
                }
                None => {
                    let len = available.len();
                    counted = counted.saturating_add(len);
                    self.inner.consume(len);
                    self.discarding = Some(counted);
                }
            }
        }
    }
}

enum Push {
    Ok,
    Oversized(usize),
}

/// Append `bytes` to the pending frame unless that would exceed `max_bytes`.
/// On overflow nothing is appended and the would-be total is returned, so no
/// allocation ever happens for a frame that is going to be rejected.
fn push(buf: &mut Vec<u8>, max_bytes: usize, bytes: &[u8]) -> Push {
    let total = buf.len().saturating_add(bytes.len());
    if total > max_bytes {
        return Push::Oversized(total);
    }
    buf.extend_from_slice(bytes);
    Push::Ok
}

/// Strip a trailing `\r` and validate UTF-8.
fn finish_frame(mut frame: Vec<u8>) -> Frame {
    if frame.last() == Some(&b'\r') {
        frame.pop();
    }
    match String::from_utf8(frame) {
        Ok(line) => Frame::Line(line),
        Err(_) => Frame::Rejected(BridgeError::malformed("frame is not valid UTF-8")),
    }
}

/// Position of the first `needle` in `haystack`.
fn memchr(needle: u8, haystack: &[u8]) -> Option<usize> {
    haystack.iter().position(|&b| b == needle)
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncWriteExt, BufReader};

    /// Collect every frame until EOF from a reader fed by `writes`, each write
    /// flushed separately so the reader observes exactly those boundaries.
    async fn drive(writes: Vec<Vec<u8>>, limit: usize) -> Vec<Frame> {
        // `duplex` returns two halves; the reader side is wrapped in a small
        // BufReader so partial reads really are partial.
        let (mut tx, rx) = tokio::io::duplex(8);
        let writer = tokio::spawn(async move {
            for chunk in writes {
                tx.write_all(&chunk).await.expect("write");
                tx.flush().await.expect("flush");
            }
            // Dropping `tx` signals EOF.
        });
        let mut reader = FrameReader::with_limit(BufReader::with_capacity(4, rx), limit);
        let mut frames = Vec::new();
        loop {
            let frame =
                tokio::time::timeout(std::time::Duration::from_secs(5), reader.next_frame())
                    .await
                    .expect("bounded")
                    .expect("io");
            let done = matches!(frame, Frame::Eof);
            frames.push(frame);
            if done {
                break;
            }
        }
        writer.await.expect("writer task");
        frames
    }

    fn chunks(parts: &[&str]) -> Vec<Vec<u8>> {
        parts.iter().map(|p| p.as_bytes().to_vec()).collect()
    }

    fn lines(frames: &[Frame]) -> Vec<String> {
        frames
            .iter()
            .filter_map(|f| match f {
                Frame::Line(s) => Some(s.clone()),
                _ => None,
            })
            .collect()
    }

    fn rejected(frames: &[Frame]) -> Vec<&BridgeError> {
        frames
            .iter()
            .filter_map(|f| match f {
                Frame::Rejected(e) => Some(e),
                _ => None,
            })
            .collect()
    }

    #[tokio::test]
    async fn reassembles_a_frame_split_across_partial_reads() {
        let frames = drive(chunks(&["{\"a\"", ":1", "}\n"]), 64).await;
        assert_eq!(lines(&frames), vec!["{\"a\":1}"]);
        assert!(matches!(frames.last(), Some(Frame::Eof)));
    }

    #[tokio::test]
    async fn splits_multiple_frames_delivered_in_one_read() {
        let frames = drive(chunks(&["{\"a\":1}\n{\"b\":2}\n{\"c\":3}\n"]), 64).await;
        assert_eq!(lines(&frames), vec!["{\"a\":1}", "{\"b\":2}", "{\"c\":3}"]);
    }

    #[tokio::test]
    async fn delivers_trailing_frame_without_newline_at_eof() {
        let frames = drive(chunks(&["{\"a\":1}\n{\"b\":2}"]), 64).await;
        assert_eq!(lines(&frames), vec!["{\"a\":1}", "{\"b\":2}"]);
    }

    #[tokio::test]
    async fn strips_carriage_return_and_keeps_blank_lines_for_the_parser() {
        let frames = drive(chunks(&["{\"a\":1}\r\n\r\n{\"b\":2}\r\n"]), 64).await;
        assert_eq!(lines(&frames), vec!["{\"a\":1}", "", "{\"b\":2}"]);
    }

    #[tokio::test]
    async fn frame_exactly_at_the_limit_is_accepted() {
        let exact = "x".repeat(10);
        let payload = format!("{exact}\n{{}}\n");
        let frames = drive(chunks(&[&payload]), 10).await;
        assert_eq!(lines(&frames), vec![exact, "{}".to_string()]);
    }

    #[tokio::test]
    async fn oversized_frame_is_skipped_without_buffering_and_reported_once() {
        let big = "y".repeat(1000);
        let payload = format!("{big}\n{{\"ok\":1}}\n");
        let frames = drive(chunks(&[&payload]), 10).await;
        let errors = rejected(&frames);
        assert_eq!(errors.len(), 1, "exactly one rejection: {frames:?}");
        assert_eq!(errors[0].code, crate::bridge::framing::code::PARSE_ERROR);
        assert!(
            errors[0].message.contains("1000"),
            "reports the observed size, got {}",
            errors[0].message
        );
        assert!(
            !errors[0].message.contains("yyyy"),
            "never echoes payload bytes: {}",
            errors[0].message
        );
        // The stream is back in sync on the very next frame.
        assert_eq!(lines(&frames), vec!["{\"ok\":1}"]);
    }

    #[tokio::test]
    async fn oversized_frame_at_eof_is_reported_then_eof() {
        let big = "z".repeat(50);
        let frames = drive(chunks(&[&big]), 10).await;
        assert_eq!(rejected(&frames).len(), 1);
        assert!(lines(&frames).is_empty());
        assert!(matches!(frames.last(), Some(Frame::Eof)));
    }

    #[tokio::test]
    async fn invalid_utf8_rejects_only_that_frame() {
        let frames = drive(vec![b"{\"m\":\"\xff\xfe\"}\n{\"ok\":1}\n".to_vec()], 64).await;
        let errors = rejected(&frames);
        assert_eq!(errors.len(), 1);
        assert!(errors[0].message.contains("UTF-8"));
        assert_eq!(lines(&frames), vec!["{\"ok\":1}"]);
    }

    #[tokio::test]
    async fn cancelled_mid_discard_resumes_skipping_the_same_line() {
        // A 1-byte duplex forces one fill_buf per byte, so a timeout dropped
        // in the middle of the skip is a real mid-line cancellation.
        let (mut tx, rx) = tokio::io::duplex(1);
        let mut reader = FrameReader::with_limit(BufReader::with_capacity(1, rx), 4);
        let feeder = tokio::spawn(async move {
            tx.write_all(b"abcdefghij\n{}\n").await.expect("write");
            tx.flush().await.expect("flush");
            // Dropping `tx` signals EOF once every byte has been consumed.
        });
        // Poll with a deadline short enough to drop the future while the
        // over-long line is still being discarded; repeat until EOF. Each
        // drop must leave the reader in a resumable state.
        let mut frames = Vec::new();
        let start = std::time::Instant::now();
        loop {
            assert!(
                start.elapsed() < std::time::Duration::from_secs(10),
                "bounded"
            );
            match tokio::time::timeout(std::time::Duration::from_micros(50), reader.next_frame())
                .await
            {
                Ok(frame) => frames.push(frame.expect("io")),
                Err(_) => continue, // cancelled mid-read; resume
            }
            if matches!(frames.last(), Some(Frame::Eof)) {
                break;
            }
        }
        feeder.await.expect("feeder");
        assert_eq!(rejected(&frames).len(), 1, "one rejection: {frames:?}");
        assert_eq!(
            lines(&frames),
            vec!["{}"],
            "no tail of the skipped line leaks"
        );
    }

    #[tokio::test]
    async fn eof_with_no_data_is_just_eof() {
        let frames = drive(Vec::new(), 64).await;
        assert_eq!(frames.len(), 1);
        assert!(matches!(frames[0], Frame::Eof));
    }

    #[test]
    fn production_limit_matches_framing() {
        let (_tx, rx) = tokio::io::duplex(1);
        let reader = FrameReader::new(BufReader::new(rx));
        assert_eq!(reader.max_bytes, MAX_FRAME_BYTES);
    }
}
