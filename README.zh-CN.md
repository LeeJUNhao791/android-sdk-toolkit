# Android SDK Toolkit

[English](README.md)

[![main 分支 SDK Toolkit CI](https://github.com/LeeJUNhao791/android-sdk-toolkit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/LeeJUNhao791/android-sdk-toolkit/actions/workflows/ci.yml)
[![最新版本](https://img.shields.io/github/v/release/LeeJUNhao791/android-sdk-toolkit)](https://github.com/LeeJUNhao791/android-sdk-toolkit/releases/latest)
[![MIT 许可证](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

用于交付和集成 Android SDK 的命令行工具。可以检查 APK 的 16 KB 对齐、从已解析的 AAR 中查找出问题的原生库、验证 AAR 交付约定，以及诊断 JNI 加载问题。脚本也可以作为 [Agent Skills](skills) 使用。

![MediaPipe APK 实际静态检查：8 项 ELF、16 项 ZIP 检查通过，并生成 JSON 与双语 Markdown](docs/assets/toolkit-demo.png)

2026-11-26 对真实 MediaPipe 调试 APK 执行后，将实际输出制作成静态可视化。安装和 JNI 运行需单独验证。[复现命令与输入哈希](docs/assets/demo.md)。

## 检查最终 APK 的 16 KB 对齐

安装 Python 3.8 或更新版本，在仓库根目录运行下列命令。检查 APK 或 AAR 不需要安装 Android SDK。

```sh
python skills/apk-page-size-check/scripts/check_apk.py app.apk
```

工具会检查 ARM64 和 x86-64 原生库的 ELF `PT_LOAD` 段和未压缩原生库在 APK 中的 ZIP 数据偏移。JSON 报告给出未对齐的条目和对应数值。拆分交付时，请对每个实际分发的 APK 分别执行检查。退出码 `0` 表示检查通过，`1` 表示对齐失败，`2` 表示输入无效或不受支持，`3` 表示 APK 没有 64 位库且无 ZIP 对齐错误。需要确认 16 KB 环境下的安装和 JNI 调用时，请在实际页大小为 `16384` 的设备或模拟器上验证。 [真机验证步骤](README.md#verify-the-aar-on-an-android-device)

通过 [16 KB 对齐故障排查](docs/16kb-troubleshooting.zh-CN.md) 修复 ELF 或 ZIP 对齐问题，并用 WebRTC 示例追溯失败库的 AAR 版本。

### 查找出问题的 .so 所在的候选 AAR

导出实际构建 APK 的模块和 variant 的 Gradle 运行时 AAR 清单，包含传递依赖。清单记录 `consumer_configuration` 和 `artifacts`，后者的每一项包含已解析的 Maven 坐标 `coordinate` 和文件路径 `path`。相对路径以清单所在目录为基准。 [清单示例和 Gradle 导出方法](README.md#find-candidate-aars-for-failing-native-libraries)

```sh
python skills/apk-page-size-check/scripts/check_apk.py app.apk --aar-manifest resolved-aars.json
```

对于每个对齐失败的库，工具比较相同 ABI 和库名的文件内容，以 SHA-256 标记 `single_candidate`、`multiple_candidates` 或 `unknown`。匹配结果以清单中提供的 AAR 为限，APK 的 ZIP 偏移由最终打包过程决定。Gradle 剥离符号后，APK 内的库可能与原始 AAR 的字节不同。遇到这种情况，可用剥离符号前的合并产物与 AAR 比对。

以下是可离线运行的合成样例。第二条命令预期返回 `1`，并分别报告唯一候选、多候选和未匹配三种结果。

```sh
python skills/apk-page-size-check/examples/generate_origins.py build/apk-origins
python skills/apk-page-size-check/scripts/check_apk.py build/apk-origins/app.apk --aar-manifest build/apk-origins/resolved-aars.json
```

### 在 GitHub Actions 中检查 APK

将这一步放在构建 APK 之后。若清单引用构建任务的本地 Gradle 缓存，请在同一个 job 运行。

```yaml
- name: Check APK 16 KB alignment
  id: alignment
  uses: LeeJUNhao791/android-sdk-toolkit@v0.9.0
  with:
    apk: app/build/outputs/apk/release/app-release.apk
    # 可选，传入已解析的 AAR 清单
    aar-manifest: build/resolved-aars.json
```

Action 将检查结果写入 Job Summary，通过 `status`、`exit-code` 和 `report` 输出结果和 JSON 路径。对齐失败或输入无效会使步骤失败。无适用 64 位库且无 ZIP 对齐错误时，步骤成功并返回 `not_applicable`。 [Action 完整用法](README.md#use-the-github-action)

- **WebRTC**。实际 Gradle APK 通过了检查。人为改变 ZIP 数据偏移的对照 APK 失败，报告列出 WebRTC AAR 候选。 [构建与检查步骤](https://github.com/LeeJUNhao791/android-delivery-workflows/blob/3101b54c63e57b06234448f50ee22e73b882451c/examples/apk-16kb-action/README.md#check-a-gradle-built-apk-with-a-third-party-sdk) · [APK 检查作业](https://github.com/LeeJUNhao791/android-delivery-workflows/actions/runs/44472134100/job/135383913161) · [运行摘要和报告](https://github.com/LeeJUNhao791/android-delivery-workflows/actions/runs/44472134100)
- **MediaPipe**。上游 Image Classification 示例的 Debug APK 通过。Gradle 剥离符号前的合并产物与传递依赖 `com.google.mediapipe:tasks-core:1.2.2` 的 AAR 内容匹配。 [构建与检查步骤](https://github.com/LeeJUNhao791/android-delivery-workflows/blob/d5f43e846744f53d0c8a90260dd32b217bf8b935/examples/apk-16kb-action/README.md#check-the-upstream-mediapipe-image-classification-apk) · [CI 证据](https://github.com/LeeJUNhao791/android-delivery-workflows/actions/runs/44480978736)

### 追溯剥离符号后的原生库

Gradle 导出示例适用于 `:app` 模块的单个 Debug APK，要求该变体未配置 `productFlavor`。从 `v0.9.0` 取出导出脚本，在构建 APK 的同一个 job 中生成 AAR 清单和溯源 JSON，再将两个文件交给 Action。 [Gradle 导出命令](README.md#trace-a-stripped-library-from-the-same-gradle-build)

```yaml
- uses: LeeJUNhao791/android-sdk-toolkit@v0.9.0
  with:
    apk: app/build/outputs/apk/debug/app-debug.apk
    aar-manifest: app/build/reports/apk-16kb/resolved-aars.json
    native-provenance: app/build/reports/apk-16kb/native-provenance.json
```

`report` 指向包含 AAR 候选的 JSON。Job Summary 显示对齐状态和候选坐标。

### 生成双语供应商沟通稿

也可用一条命令扫描最终 APK，并保存 JSON 和中英文 Markdown 草稿：

```sh
python skills/apk-page-size-check/scripts/check_apk.py "app with spaces.apk" --aar-manifest resolved-aars.json --native-provenance native-provenance.json --output-dir "build/apk evidence/run-1"
```

两个附加清单参数均可省略；使用 `--native-provenance` 时必须同时提供 `--aar-manifest`。输出目录必须尚不存在，重试时也要使用新目录。命令将 UTF-8 的 `report.json` 和 `report.md` 写入该目录，标准输出仍为扫描 JSON。输入无效时也会保存 JSON 和明确标注输入无效的 Markdown。证据生成完成后，保留扫描退出码 `0`、`1`、`2`、`3`；目录创建或报告生成出错时返回 `2`，并写出错误提示。若扫描已完成，标准输出中的 JSON 状态和已写出的文件都会保留。因此应同时核对命令退出码、错误提示和 JSON 状态，确认本次证据是否完整生成。

保存检查器 JSON，再生成中英文 Markdown 草稿。请分别执行两条命令：对齐失败时，第一条返回退出码 `1`，仍会写出 JSON。

```sh
python skills/apk-page-size-check/scripts/check_apk.py app.apk --aar-manifest resolved-aars.json > apk-16kb.json
python skills/apk-page-size-check/scripts/render_vendor_report.py apk-16kb.json -o vendor-report.md
```

对于剥离符号的库，在第一条命令中加入同次构建的 `--native-provenance native-provenance.json`。
对于 ELF 失败项，草稿会列出可用的 APK 内 SO SHA-256。唯一的直接字节匹配会补充 AAR 坐标和条目；若符号剥离链通过验证且只有一个 AAR 候选，还会列出剥离符号前 SO 的 SHA-256。这些摘要标识 SO 内容，不是完整 APK 或 AAR 的摘要。仅 ZIP 失败时，建议由应用打包侧处理。已验证的符号剥离链会先要求复查 AAR 条目的 ELF 对齐，再确定是否需要供应商修复。

请指定一个新输出文件；生成器会保留已有文件。成功写出草稿时返回 `0`，JSON 不可用或输出失败时返回 `2`。分享前请复核；草稿会省略本地路径。16 KB 系统上的安装和 JNI 调用仍需单独验证。 [报告生成说明](docs/16kb-troubleshooting.zh-CN.md#生成双语供应商沟通稿)

## 其他交付工具

| 场景 | 用法 |
| --- | --- |
| 检查 AAR 是否包含约定的 ABI、文件和 R8 规则 | `python skills/aar-delivery-check/scripts/check_aar.py vendor.aar --expect skills/aar-delivery-check/examples/expect.json --verify-abi`。按实际交付内容调整 JSON 清单。 [AAR 检查](README.md#aar-delivery-check) |
| 诊断 JNI 加载或方法绑定错误 | `python skills/android-jni-doctor/scripts/jni_doctor.py app.apk --abi arm64-v8a --log app-log.txt`。请使用出错设备实际选择的 ABI 和同一次运行的日志。 [JNI 诊断](README.md#jni-load-diagnosis) |
| 发布 AAR 或 JAR 至本地 Maven 仓库，验证独立消费者可使用 | `skills/android-sdk-pack/scripts/publish_sdk.py` 校验实际解析到的 Maven 坐标、制品 SHA-256 和 smoke task。 [交付验证命令和构建依赖](README.md#package-and-verify-an-sdk-handoff) |

[SDK Toolkit CI](https://github.com/LeeJUNhao791/android-sdk-toolkit/actions/workflows/ci.yml) 在 Windows 和 Linux 运行命令行测试，并在 Linux 构建真实的 AAR/JAR 示例、验证消费者和 APK 对齐。

## 许可证

[贡献指南](CONTRIBUTING.md) · [MIT](LICENSE)
