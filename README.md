# ZB Studio

当前桌面版本：`0.5.2`。

## 安装包与更新

从 [GitHub Releases](https://github.com/christiancagfr-alt/ZBstudio/releases) 下载对应平台的安装包。应用的“系统设置 → 检查更新”会读取最新 Release；只会下载包含 SHA-256 清单且校验通过的当前平台安装包。用户工作表、Google 授权和本地下载路径保存在各自系统的用户数据目录，既不随安装包发布，也不会被更新覆盖。

Python / PySide6 桌面视频任务工作台，支持 Windows、macOS 与 Linux。

## 开发与构建

使用 Python 3.12，在虚拟环境内安装：

```sh
python -m pip install --upgrade pip==26.2.2
python -m pip install -r requirements-dev.txt
python -m pytest -q
python build_desktop.py
```

桌面入口为 `desktop_entry.py`。源码启动时设置 `PYTHONPATH=src`，运行 `python -m zb_studio.desktop`。
GitHub Actions 在三种系统分别运行测试、构建和启动检查，压缩包在对应运行的 Artifacts 下载。macOS 为 runner 的原生架构；程序暂未签名或公证。

## Google 与素材

在系统设置导入自己的 Google Desktop OAuth JSON，再进行 Google 授权。使用 Sheets、Drive 文件写入及 Drive 只读权限。登录存入系统凭据库；Linux 需要已解锁的 Secret Service。旧版本升级后需要重新授权文件夹读取权限。

图片目录：`领取日期/需求日期/需求者 人物分类/序号.png`。
云端文件夹目录：`领取日期/需求日期/需求者 人物分类/序号/`。
目录内按原文件名自然顺序下载：图片 `01-1.png`、`01-2.jpg`，视频独立从 `01-1.mp4` 开始。子文件夹递归保留，其他文件放在“附件”中。Google 文档与幻灯片导出 PDF，电子表格导出 XLSX。快捷方式及不能导出的云端类型会明确报错；不会报告为全部成功。
单次目录上限 10000 项、20 层、20 GB。已有文件不覆盖，相同内容重试复用。下载不执行任何文件。

跨工作簿操作不具备原子性。多人协同的中心协调器、完整角色权限与中断后上传续传尚未实现；遇到回填失败请先核对操作记录，避免重复领取或上传。

日志、登录凭据、审核资料和本机诊断文件不属于源码发布内容。
