# Cycle Pages 发布恢复（2026-11-11）

## 已确认原因

- Pages API：`build_type=legacy`，发布源 `main:/docs`，正式地址 `https://tammyuuuu.github.io/MagicCycle/`。自动工作流为 `dynamic/pages/pages-build-deployment`，本地没有 `.github/workflows` 并不是缺失配置。
- 旧运行 `42633119702` 第一次尝试：构建和上传产物成功；部署于北京时间 11 月 9 日 22:17 开始，在 `syncing_files` 阶段停留，22:27 超过 600000ms 后失败。后续重试排队超过 36 小时。日志只能确定 GitHub Pages 文件同步超时，未揭示服务端内部原因。
- 本地 `logs/auto_update.log`：11 月 11 日已生成并提交 `eecb15a`，但 SSH 代理 `127.0.0.1:7897` 返回 `errno=10061`，推送失败。原 SSH 配置强制经由本机 SOCKS 代理；检查时 HTTPS 经已有代理可正常连接，绕过代理的直连不可用。
- 修复前远程 `main=cf067fb`，本地领先 1 个提交；另有 13 个行情缓存文件未提交，合计增加 20 行、删除 3 行。没有分叉，不需要合并或重置。

## 实际修复

- 取消滞留的旧部署重试。
- 仅本仓库 origin 改用 HTTPS，并为 GitHub 配置现有 `gh auth git-credential` 凭据助手；未修改全局代理和 SSH 配置。
- 正常快进推送已有页面提交 `eecb15a`，保留 `main:/docs` 发布方式。
- 更新 `update_alerts.ps1`：去掉强制 SSH 环境配置；推送前验证静态产物，推送后等待并校验线上发布，全部通过才输出 SUCCESS。
- 新增只读 `verify_pages_release.py` 和 5 项回归测试；更新 README 中的发布和故障排查说明。
- 未重新生成行情、修改策略或覆盖页面。13 个已有缓存修改保留且没有纳入修复提交。

## 验证结果

- 恢复部署 `42949472468`：构建、部署、状态回报全部成功，北京时间 11 月 11 日 10:57:59 完成。
- 本地和线上发布版本均为 `7c4300d346d55f3cb4d4`；清单内 15 项资源的线上原始字节 SHA-256 全部通过。
- `index.json`、`purchase_monitor.json`、`account_nav.json`、`bundle-assets.json` 与本地内容一致，`sw.js` 与本地发布版本一致。首次线上校验遇到临时 TLS EOF，第二次完整校验通过。
- 页面更新时间为 2026-11-11 10:23。7 只 ETF 快照数据日均为 2026-11-10。此核对证明线上数据与已有本地快照相符，不代表独立向行情供应商重新核验。
- 个股入口属于首页“今日提醒 → 个股”选项卡，并非单独 `/stock.html` 页面。浏览器已显示 NVIDIA、Microsoft 等个股卡片和判断依据。其行情仍为 2026-11-06 的缓存，页面保留缓存提示；发布恢复不等于个股行情已更新。
- 浏览器从旧 PWA 版本显示“新版本已就绪”，点击“刷新更新”成功切换到新版。未清理 localStorage、IndexedDB 或用户账本。
- 今日提醒、投资配置、投资复盘和策略实验页面均加载成功；配置页加载完成、复盘显示空账户状态、实验页展示历史区间及策略卡片。
- `python -B -m unittest test_pages_release -v`：5/5 通过，覆盖完整发布、旧版本、损坏资源、旧行情 JSON、旧 Service Worker。
- PowerShell 语法解析和 `git diff --check` 通过。

本轮按后续指令聚焦恢复正式发布。Test 的行情安全机制迁移未包含在本轮修复中。
