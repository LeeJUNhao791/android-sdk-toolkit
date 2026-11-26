# Demo evidence / 演示依据

The PNG is a static visualization of selected fields from an actual run on 2026-11-26, not a screen recording. It uses Google's compiled MediaPipe Image Classification debug APK, not a synthetic archive. No APK is distributed here.

PNG 是 2026-11-26 本轮实际输出的静态可视化，不是录屏。输入是实际编译的 Google MediaPipe 图像分类调试 APK，不是合成归档；本仓库不分发 APK。

| Evidence / 依据 | Value / 值 |
| --- | --- |
| Toolkit source base / 工具源码基线 | `1451e73a2b0c23ab8c243698134cf463be9dd2fd` |
| MediaPipe source / 输入源码 | [`46d60d66baf21ae91977c488ea0875f0e13c4d2b`](https://github.com/google-ai-edge/mediapipe-samples/tree/46d60d66baf21ae91977c488ea0875f0e13c4d2b/examples/image_classification/android) |
| APK SHA-256 | `abfdbc8b45775414f315509675ad1577b7bf0afdcdd7f4c3c0a562e80d06cfb8` |
| Result / 结果 | `status=pass`, exit / 退出码 `0`, page size / 页大小 `16384` |
| Native library entries / 原生库条目 | `16` |
| ELF | `8` 64-bit pass / 64 位通过; `8` 32-bit `not_applicable` / 32 位不适用 |
| ZIP | `16` pass / 通过 |
| Generated / 已生成 | `report.json`, Chinese + English / 中英双语 `report.md` |

## Reproduce / 复现

From this repository's root, use Python 3.8+ and an APK you are authorized to inspect. Replace the input path. The output directory must be new. To build the pinned MediaPipe sample, follow the [existing build guide](https://github.com/LeeJUNhao791/android-mcp-inspector/blob/7b390bd1f845f70e87c7f1b3208a6281cf883522/examples/mediapipe.md); no provenance inputs are required for this alignment-only demo. Rebuilds may produce a different APK hash.

在本仓库根目录，用 Python 3.8+ 检查你获准使用的 APK。替换输入路径，输出目录必须尚不存在。可按[已有构建说明](https://github.com/LeeJUNhao791/android-mcp-inspector/blob/7b390bd1f845f70e87c7f1b3208a6281cf883522/examples/mediapipe.zh-CN.md)构建固定版本的 MediaPipe 示例；本演示仅检查对齐，不需要溯源输入。重新构建的 APK 哈希可能不同。

```sh
python skills/apk-page-size-check/scripts/check_apk.py path/to/app-debug.apk --output-dir build/demo-report
```

Open `build/demo-report/report.json` for every library and `build/demo-report/report.md` for the bilingual report. The image counts were calculated from this run's JSON, and the quoted English sentence comes from its generated Markdown.

在 `build/demo-report/report.json` 逐库核对，`build/demo-report/report.md` 为双语报告。图片中的数量来自本轮 JSON，英文建议原句来自本轮生成的 Markdown。

This run covers static APK ELF and ZIP alignment. It does not establish AAR attribution, device installation, JNI execution, or compatibility of a different build.

本轮范围是 APK 的 ELF、ZIP 静态对齐；未验证 AAR 来源、设备安装、JNI 运行或其他构建的兼容性。
