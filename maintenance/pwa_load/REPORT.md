# 星循加载与 PWA 更新验收

日期：2026-10-23。正式页面使用现有 `python -B export_alerts.py --offline` 生成，没有手工覆盖 HTML。未运行 Git 提交/推送或自动发布脚本。

## 前后测速

同一 Chrome headless、375×812 手机尺寸、冷缓存、每请求80ms延迟、约1.5MB/s每连接，3次中位数。测速禁用SW以公平比较首个页面资源，未模拟手机CPU；不能当作真机或公网承诺。

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| HTML未压缩大小 | 9,470,815字节 | 109,255字节 |
| DOM/导航就绪 | 7,931ms | 331ms |
| 首次内容绘制FCP | 224ms | 208ms |
| 首屏长任务累计 | 1,030ms | 0ms |
| 测量窗口内传输资源 | 9,752,721字节 | 390,716字节 |

主要改善是显示后的等待和导航就绪；原来的HTML流式响应已经较早绘制首屏，因此不能宣传为视觉首屏快24倍。原始结果见 before_metrics.json / after_metrics.json。旧版来自Git提交 db9659fba53c63fa5ba7d19242761e57988ada08，可复现。

## 实现

- 首次仅执行轻量今日监测、导航和账户只读访问；未打开非首页时不存在 XingxunWorkspace，研究曲线未解析。
- 投资配置/复盘首次打开时加载完整公开净值、账户运行代码；首次打开策略实验时才解析完整研究曲线。数据没有裁剪或改变算法。
- 哈希命名的不可变 bundles，导出自动生成资源清单、SHA-256校验和SW发布版本。
- 缓存优先打开首页。加载后、回到前台、网络恢复及每分钟后台检查SW更新。新资源安装完整后提示用户刷新，点击才激活；其他打开的页面不会被强制刷新。
- 安装失败、清单版本不一致或资源哈希不一致不激活；保留上一版缓存供旧页面继续加载。相同曲线从旧缓存复用。
- localStorage/IndexedDB 不删除、不改名，不改变站点路径或账本存储键。更新前有填写时允许取消刷新。
- 自动发布入口 update_alerts.ps1 同批提交HTML、bundles、清单和SW。实时account_nav.json不参与固定版本完整性校验，避免后台净值刷新导致安装失败；账户bundle包含原有公开净值快照用于离线。

更新流程参考 [MDN Service Worker 生命周期](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers) 和 [Chrome PWA更新](https://web.dev/learn/pwa/update)。

## 验证

- 根目录Node测试：98/98通过。两个原依赖实时行情日期的历史用例固定合成日期/NAV；源装配断言区分Flask内联与静态bundle。
- test_purchase_monitor Python：8/8通过；发布脚本PowerShell解析通过。
- check_mobile_preview.js：320/375/390/430四种宽度的四页、下拉选择、表单、刷新均通过。
- test_upgrade.js / maintenance/20261022/test_pwa.js：真实旧HTML和v50 SW → 新拆分版本 → 下一版本；测试 /cycle/ 子目录托管。
- 已确认买入记录、账户比例、研究选择、估值年限等 localStorage 所有键值在两次升级前后逐字相同。
- 已验证新版本等待提示、用户确认刷新、取消未保存内容刷新、安装失败继续旧版、二次更新复用研究缓存、四页离线导航与重新打开，不需要卸载重装。
- 浏览器移动尺寸验证通过；没有访问或操作用户手机中的真实账本，真机尚未实测。

## 重跑

```powershell
node maintenance/pwa_load/benchmark.js before
node maintenance/pwa_load/benchmark.js after
node maintenance/20261022/test_pwa.js
```
