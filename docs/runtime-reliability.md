# 3D 战斗与输入修复

验证时间：2026-11-22T12:58:03.104Z。运行时 SHA256：`9f546f40e5ab2d6e7f074f20375f74a215e843e2cd9ca6391402c16dfc1731b3`；人物 GLB：`e410803590a90e19e9d3f1182f07a523c50187717bde56162394d57487b591d2`。

| 缺陷 | 原生产代码复现 | 当前验收 |
|---|---|---|
| 击杀血条 | 斩击后仍 8.6111%，剑芒后仍 15%，实际 bossHP 已为 0 | 两种致命帧同步为 0%，结果不可反转 |
| 闪避补刀 | 闪避结束旧 attack 计时继续，无新输入时 bossHP 360→329 | 闪避取消未完成命中，期间不允许施法覆盖 |
| 闪避方向 | 重试沿用上局 move；同帧新方向未进入 move | 起手根据当前输入与相机重算 |
| 输入源相互清除 | 键盘与触屏共用 Set；松开任一即清整方向 | Keyboard Set + pointerId Map 聚合，多源独立释放 |
| 延迟 lostpointercapture | 旧手指事件清掉新手指按住的方向 | 只清对应 pointerId 的当前方向 |
| 当前标签重置 | 点击演武场令 battle→ready | 同模式导航保留进度与暂停 |
| 页面隐藏 | 无 blur 时缺少暂停入口 | visibilitychange/pagehide 暂停并清旧输入，显式恢复 |

[生产代码回归报告](viewer-verification.json) 包含 14 组行为测试；同时保留 10 组模型取景和 25 轮观察切换。测试使用实际 GLB、Three.js AnimationMixer/OrbitControls 和生产函数，DOM 矩形为确定性测试数据。

真实浏览器入口为 `node tools/validate-browser.mjs`。本环境在 Chromium 启动阶段失败，退出 2；详细状态见 [浏览器报告](browser-verification.json)。此次发布没有浏览器 GPU、CSS 或设备性能通过的结论。
