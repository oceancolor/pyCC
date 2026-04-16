// 原始 TS: utils/clipboard.ts
//! 跨平台剪贴板工具

pub fn copy_to_clipboard(text: &str) -> anyhow::Result<()> {
    // 尝试 xclip / xsel / pbcopy / clip.exe
    todo!()
}

pub fn read_from_clipboard() -> anyhow::Result<String> {
    todo!()
}
