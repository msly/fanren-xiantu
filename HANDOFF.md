# 凡人仙途 · 接手记录

更新：2026-11-22T21:02:05+08:00（北京时间）。**候选已验收，待完成部署核验**。当前韩立 revision 6，运行时 `20261122-runtime1`；共同基线 `8c552c0fc6dc7f976d9aeb97fb08ae5bf009a832`。

## 本轮完成

- 接续此前完整上传但未进入主线的 v6 人物包；保留 CC0 头部/贴图来源文件、21 骨骼和 Idle/Walk/Attack 接口。
- 修复最终侧面渲染发现的右后低颈穿领；旧模型四条缺陷射线失败，新模型 7/7 通过。脸部、非皮肤网格及动作采样未改。
- 修复击杀 HUD、闪避补发旧斩击、陈旧闪避方向、键盘与多触点归属、当前标签重置和隐藏页面暂停；新增 14 组生产事件/状态回归通过。
- 最终资产、CPU 动作、观察模式与战斗回归全部通过。最终 GLB 重新导入 Blender，13 张独立静态/动作图片与报告统一到同一资产哈希。
- 浏览器验收脚本 `tools/validate-browser.mjs` 已纳入；本次 Chromium 在导航前 socket EPERM，GPU/CSS/FPS/手机性能仍未验收。

## 当前资产与证据

- 韩立 GLB：`e410803590a90e19e9d3f1182f07a523c50187717bde56162394d57487b591d2`，16,520,736 字节，268,652 三角面，29 材质分片、15 纹理。
- 韩立 BLEND：`be0a68c87a374989a2b107a83a7e35d4daa68ef952890c107f83b96fe7c7e969`。
- 验收：`docs/3d-verification.json`；运行时：`docs/viewer-verification.json`；领口：`docs/collar-verification.json`；最终图片：`docs/hanli-v6-render-manifest.json`。
- 部署结果：`docs/runtime-release-delivery.json`。旧 `docs/release-delivery.json` 是 revision 5 的历史发布凭据。

## 下一阶段

1. 在可启动浏览器的环境运行 `tools/validate-browser.mjs`，补真实 WebGL、CSS 和交互截图；单独在目标手机测帧率和加载耗时。
2. revision 6 相对 v5 三角面 +48.3%、GLB 文件 +86.4%；先测真实渲染预算，再决定纹理压缩和 LOD。
3. 继续面部神态、头发体积和衣摆折面；随后改进动作重量转移、移动速度与步幅匹配。3D 仍是单场试炼，完整剧情迁移未完成。

## 路径与交接约束

- 主仓库：`/data1/workspace/github/fanren-xiantu`。
- 静态部署：`/home/appops/fanren-game`，8090 端口。
- 本轮隔离分支：`fix/combat-runtime-707c`，工作树 `../fanren-runtime-707c`；此前 `../fanren-xiantu-v6-8c9b281c` 与传输包未被修改。
- 后续接手以最新 main 为准，不要把旧 v6 `core.tar.gz` 整包再次覆盖：它含已修复前的颈部网格，也没有本轮战斗修复。
- 重建会改变 GLB/Blend 与生成器哈希，须重新验证、重渲并更新报告。脚底数值检查不代表物理脚锁；固定射线回归不代表所有角度/所有动作都已自动验证。

## 入口

- [3D 试炼](http://23.82.99.226:8090/game3d.html?v=20261122-character6-runtime1)
- [韩立半身](http://23.82.99.226:8090/game3d.html?v=20261122-character6-runtime1&view=hero&frame=portrait)
- [韩立头部](http://23.82.99.226:8090/game3d.html?v=20261122-character6-runtime1&view=hero&frame=head)
