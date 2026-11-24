# APK 16 KB 对齐故障排查

[English](16kb-troubleshooting.md)

在 Toolkit 仓库根目录运行以下命令，将 `app-release.apk` 换成准备分发的已签名 APK。拆分交付时，请逐个检查实际分发的 APK。

```sh
python skills/apk-page-size-check/scripts/check_apk.py app-release.apk
```

## 按失败项修复

- **`elf: fail`** 表示 `.so` 内有 `PT_LOAD` 段未通过对齐检查。重新编译该库，使其满足 16 KB ELF 对齐。NDK r28 及更高版本默认启用 16 KB 对齐。如果库来自预编译 SDK，升级到包含兼容原生库的版本，或请供应商提供重编后的 AAR。重新构建应用并检查最终 APK。 [Android 编译说明](https://developer.android.com/guide/practices/page-sizes?hl=zh-cn#compile-16-kb-alignment)
- **`zip: fail`** 表示未压缩的 `.so` 在 APK 内的起始偏移未对齐。Gradle 项目如需继续使用未压缩的原生库，请使用 Android Gradle 插件 8.5.1 或更高版本。自定义打包流程如果使用 `apksigner`，先用 `zipalign -P 16 -v 4 unsigned.apk aligned.apk` 对齐未签名的 APK，再签名 `aligned.apk`。用上面的 Toolkit 命令和下面的 Android 构建工具命令复查最终已签名的 APK。下面两个命令可用 Build Tools 的完整路径执行，也可以将工具目录加入 `PATH`。 [Android 打包说明](https://developer.android.com/guide/practices/page-sizes?hl=zh-cn#update-packaging) · [zipalign](https://developer.android.com/tools/zipalign?hl=zh-cn)

```sh
zipalign -c -P 16 -v 4 app-release.apk
apksigner verify app-release.apk
```

## 追溯失败库的 AAR 版本

导出构建该 APK 的 Gradle 变体实际解析到的 AAR，包括传递依赖。用 `--aar-manifest` 将清单交给检查工具，在 `libraries` 中找到失败的库。`origin.status` 为 `single_candidate` 时，表示清单里恰好有一个 AAR 包含字节完全相同的库。从 `origin.candidates[].coordinate` 读取版本，并对照同一变体实际解析到的依赖确认。如果 Gradle 剥离符号后改变了库的字节，请使用同一次构建的溯源记录。 [导出已解析的 AAR](../README.zh-CN.md#查找出问题的-so-所在的候选-aar) · [追溯剥离符号后的原生库](../README.zh-CN.md#追溯剥离符号后的原生库)

公开发布的 WebRTC AAR `io.github.webrtc-sdk:android:104.5112.10` 包含 `jni/arm64-v8a/libjingle_peerconnection_so.so`。在已签名的 ARM64 检查样本中，该库的三个 `PT_LOAD` 段的 `p_align` 都是 `4096`，所以报告为 `elf: fail`、`zip: pass`，对应版本显示为 `single_candidate`。用相同方式打包 `150.7871.01` 后，三个段的 `p_align` 都是 `16384`，两项检查均通过。清单显式提供候选 AAR，两份样本均满足 16 KB ZIP 对齐。这组结果验证了 ARM64 的 ELF 与 ZIP 布局。评估 SDK 升级时，请在自己的应用中构建并进行运行测试。 [WebRTC 104.5112.10](https://repo.maven.apache.org/maven2/io/github/webrtc-sdk/android/104.5112.10/) · [WebRTC 150.7871.01](https://repo.maven.apache.org/maven2/io/github/webrtc-sdk/android/150.7871.01/)

## 复现 WebRTC 对照结果

准备 Python 3.8+、JDK 17（设置 `JAVA_HOME`）、Android SDK Platform 35 和 Build Tools 36.0.0（设置 `ANDROID_HOME`）。在仓库根目录按英文版的共用步骤运行，会从 Maven Central 下载两个固定版本的 AAR，生成并签名两个最小检查 APK。分别运行检查命令，旧版退出码为 `1`，且只有该版本一个候选。新版退出码为 `0`，`elf` 和 `zip` 均为 `pass`。 [复制复现脚本与检查命令](16kb-troubleshooting.md#reproduce-the-webrtc-comparison)
