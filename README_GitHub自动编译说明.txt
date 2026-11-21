服装记工本 V1.0 - GitHub 云端自动编译包
========================================

一、这个压缩包是什么
本包已放入 GitHub Actions 自动编译配置。把整个文件夹上传到自己的 GitHub 仓库后，GitHub 云端 Linux 环境会调用 Buildozer 编译 Android Debug APK，并把 APK 作为 Artifact 提供下载。

注意：这是“自动编译配置包”，不是已经编译好的 APK。云端编译是否成功，以 GitHub Actions 的实际运行结果为准。

二、上传到 GitHub
1. 登录 https://github.com/ 并创建一个新仓库。
2. 仓库建议设为 Private（私有），避免公开源码。创建时可不勾选 README、License 或 .gitignore（本包已有文件）。
3. 解压本 ZIP。
4. 将解压后文件夹里的所有内容上传到仓库根目录。特别注意：必须连同隐藏目录 .github 一起上传；其中包含 workflows/android.yml。
5. 确认仓库根目录能看到 main.py、buildozer.spec、icon.png，以及 .github/workflows/android.yml。

三、启动编译
方法 A：手动启动（推荐第一次使用）
1. 打开 GitHub 仓库。
2. 点击顶部 Actions。
3. 左侧选择 Android APK Build。
4. 点击 Run workflow，再点绿色的 Run workflow。
5. 等待任务完成。第一次下载 Android SDK/NDK 和 Gradle，可能需要较长时间。

方法 B：自动启动
以后把修改后的代码 push 到 main 或 master 分支，会自动启动编译。

四、下载 APK
1. 在 Actions 页面点开最新一次运行记录。
2. 等待状态变成绿色成功（Success）。
3. 在运行记录页面底部 Artifacts 区域，点击 fuzhuang-jigongben-android-apk 下载。
4. 解压下载的 Artifact，里面就是 APK 文件。
5. 把 APK 传到 Android 手机安装。手机可能要求允许浏览器或文件管理器安装未知来源应用。

五、失败怎么办
1. 如果显示红色 Failed，点开失败的任务 Build Android APK。
2. 展开红色报错步骤。
3. 复制日志最后约 50 行发给我，我可以根据实际错误修改配置。
4. 不要只看最上面的错误提示；通常日志末尾会显示真正失败原因。

六、隐私与费用提醒
- 建议使用 Private 仓库保存个人源代码。
- GitHub Actions 的免费额度、Artifact 保留和私有仓库限制会随账户与政策变化，请以 GitHub 账户的 Billing/Actions 页面为准。
- 本工作流只读取仓库代码并上传构建产物，不会自动发布到 Google Play。

七、当前源码功能状态（重要）
当前 main.py 是服装记工本 V1.0 基础试运行源码，已包含多明细账单、工价记忆、工资周期基础计算、分次发放金额校验和本地 SQLite 基础功能。
仍未完成或未充分验证的内容包括：历史账单编辑界面、历史工资周期浏览、发放记录编辑/删除、完整备份恢复、自动备份保留策略，以及完整实机测试。
因此，即使 APK 编译成功，也只代表“打包成功”，不代表所有业务功能已完整或经过稳定性验证。重要账目请先备份，安装后先用测试数据验证。

八、技术说明
- 构建方式：GitHub Actions + ArtemSBulgakov/buildozer-action + Buildozer。
- 目标最低 Android API：26（Android 8.0）。
- 目标 API：36；NDK：28c；架构：arm64-v8a、armeabi-v7a（沿用当前项目配置）。
- 数据库：SQLite，本地保存。
- 当前权限配置为空；本地记账基础功能不需要网络权限。
