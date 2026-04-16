#!/usr/bin/env python3
"""
fix-file-persistence-types.py
补全缺失的 src/utils/filePersistence/types.ts
运行方式：python fix-file-persistence-types.py
"""
import os

ROOT = r"F:\Claude code src"

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  OK {path}")

print("=== fix-file-persistence-types ===")

# src/utils/filePersistence/types.ts
write(os.path.join(ROOT, "src", "utils", "filePersistence", "types.ts"), """\
/**
 * types.ts — stub for filePersistence module
 * All constants / types required by filePersistence.ts and outputsScanner.ts
 */

// ── Constants ────────────────────────────────────────────────

/** Max parallel uploads when pushing to Files API */
export const DEFAULT_UPLOAD_CONCURRENCY = 5

/** Max number of files allowed per persistence run */
export const FILE_COUNT_LIMIT = 100

/** Sub-directory name inside the session outputs folder */
export const OUTPUTS_SUBDIR = 'outputs'

// ── Types ────────────────────────────────────────────────────

/** Opaque brand for turn start timestamps */
export type TurnStartTime = number & { readonly __brand: 'TurnStartTime' }

export function makeTurnStartTime(ms: number): TurnStartTime {
  return ms as TurnStartTime
}

/** A file that was successfully uploaded / persisted */
export type PersistedFile = {
  filename: string
  file_id: string
}

/** A file that failed to upload / persist */
export type FailedPersistence = {
  filename: string
  error: string
}

/** Payload emitted by the file-persistence analytics event */
export type FilesPersistedEventData = {
  files: PersistedFile[]
  failed: FailedPersistence[]
}
""")

print("\n=== 完成！===")
print("下一步：")
print("  bun run build.ts 2>&1 | Select-Object -First 50")
