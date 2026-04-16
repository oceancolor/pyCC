// Original TS source: utils/bufferedWriter.ts
// Buffered writer utility for batching writes

use std::sync::{Arc, Mutex};
use tokio::time::{Duration, Instant};

pub type WriteFn = Box<dyn Fn(&str) + Send + Sync>;

#[derive(Clone)]
pub struct BufferedWriter {
    inner: Arc<Mutex<BufferedWriterInner>>,
}

struct BufferedWriterInner {
    write_fn: WriteFn,
    buffer: Vec<String>,
    buffer_bytes: usize,
    flush_interval_ms: u64,
    max_buffer_size: usize,
    max_buffer_bytes: usize,
    immediate_mode: bool,
    last_flush: Option<Instant>,
}

impl BufferedWriter {
    pub fn new(
        write_fn: WriteFn,
        flush_interval_ms: u64,
        max_buffer_size: usize,
        max_buffer_bytes: usize,
        immediate_mode: bool,
    ) -> Self {
        Self {
            inner: Arc::new(Mutex::new(BufferedWriterInner {
                write_fn,
                buffer: Vec::new(),
                buffer_bytes: 0,
                flush_interval_ms,
                max_buffer_size,
                max_buffer_bytes,
                immediate_mode,
                last_flush: None,
            })),
        }
    }

    pub fn write(&self, content: &str) {
        let mut inner = self.inner.lock().unwrap_or_else(|e| e.into_inner());

        if inner.immediate_mode {
            (inner.write_fn)(content);
            return;
        }

        inner.buffer.push(content.to_string());
        inner.buffer_bytes += content.len();

        let should_flush = inner.buffer.len() >= inner.max_buffer_size
            || inner.buffer_bytes >= inner.max_buffer_bytes;

        if should_flush {
            let content = inner.buffer.join("");
            (inner.write_fn)(&content);
            inner.buffer.clear();
            inner.buffer_bytes = 0;
            inner.last_flush = Some(Instant::now());
        }
    }

    pub fn flush(&self) {
        let mut inner = self.inner.lock().unwrap_or_else(|e| e.into_inner());
        if inner.buffer.is_empty() {
            return;
        }
        let content = inner.buffer.join("");
        (inner.write_fn)(&content);
        inner.buffer.clear();
        inner.buffer_bytes = 0;
        inner.last_flush = Some(Instant::now());
    }

    pub fn dispose(&self) {
        self.flush();
    }
}

impl Drop for BufferedWriter {
    fn drop(&mut self) {
        self.flush();
    }
}

/// Builder for BufferedWriter
pub struct BufferedWriterBuilder {
    flush_interval_ms: u64,
    max_buffer_size: usize,
    max_buffer_bytes: usize,
    immediate_mode: bool,
}

impl BufferedWriterBuilder {
    pub fn new() -> Self {
        Self {
            flush_interval_ms: 1000,
            max_buffer_size: 100,
            max_buffer_bytes: usize::MAX,
            immediate_mode: false,
        }
    }

    pub fn flush_interval_ms(mut self, ms: u64) -> Self {
        self.flush_interval_ms = ms;
        self
    }

    pub fn max_buffer_size(mut self, size: usize) -> Self {
        self.max_buffer_size = size;
        self
    }

    pub fn max_buffer_bytes(mut self, bytes: usize) -> Self {
        self.max_buffer_bytes = bytes;
        self
    }

    pub fn immediate_mode(mut self, immediate: bool) -> Self {
        self.immediate_mode = immediate;
        self
    }

    pub fn build(self, write_fn: WriteFn) -> BufferedWriter {
        BufferedWriter::new(
            write_fn,
            self.flush_interval_ms,
            self.max_buffer_size,
            self.max_buffer_bytes,
            self.immediate_mode,
        )
    }
}
