# 凡人仙途 · 3D 接手记录

更新：2026-11-22 19:05，北京时间；本轮发布收尾完成。当前韩立资产 revision 5，基础提交为 `e51eda5e2957b3555b117bab9e62aaeac58bf3c7`；本次一并接上第四轮未完成发布的参考图改造。

## 已完成

- 发布已完成：两包全部上传、整包 SHA256 与 33 个文件校验通过，已同步至 `/home/appops/fanren-game`。2026-11-22 19:05（北京时间）从公网入口下载全部 18 个部署文件，HTTP 200，响应字节与仓库和部署目录一致；证据见 `docs/release-delivery.json`。
- 本次接续重新执行资产加载、CPU 动画、观察模式和 JS 语法检查，全部通过；细项报告已更新。

- 韩立真实 Blender/GLB：短下颌、眉眼鼻唇体积、暖肤色分区、发际碎束与背发分层、收敛袖型、抬高衣领、自然弯指和精简肩腰饰。
- 21 根骨骼及 Idle/Walk/Attack 保留；三角面 181,170，35 个材质分片，13 张内嵌纹理。
- 半身观察已接入；页面和模型 URL 使用 `20261122-character5` 缓存版本。
- 脚部倾角补偿及实际鞋底蒙皮顶点驱动的骨盆高度烘焙；稳定行走支撑脚最高约 10 mm，新增硬门为 12 mm。
- 资产加载、CPU 动画和观察模式三份报告 PASS。96 组起始相位/淡化组合、2,592 时刻，最坏脚底 +0.4919 mm。四个定点动作渲染未见已知穿插回退。
- 实际资产 SHA256：`25c2276513dee1366b148573f99212748e096df49fa5274b481cd1b6e245f558`。发布核对结果见 `docs/3d-verification.json`。

## 验证口径与继续方向

- 实际 GLB 导回 Blender 渲染，图片与报告绑定相同资产哈希；对照使用相同灯光和相机。不要用未导出的源材质效果代替运行时资产验证。
- GPU/CSS/FPS/手机性能尚未验收。Chromium 在启动阶段受环境限制，Cloud Browser 的证书/访问限制也未绕过。可在具备浏览器权限的开发环境补做真实页面验收。
- 面部神态、皮肤细节仍是程序化风格；头发为封闭发束，尚非生产级发卡或真实发丝。裙摆使用蒙皮，最大步幅仍可见角状折面。
- 行走有烘焙离地余量，没有物理脚锁、完整脚跟—脚尖重心转移，也未按游戏移动速度重建跑步动作。后续应优先做面部及毛发资产质量，再处理动作和布料。
- 墨蛟本轮保持原资产；3D 仍是独立单场试炼，不是完整 3D 剧情迁移。

## 路径与重建

- 服务器仓库：`/data1/workspace/github/fanren-xiantu`
- 静态部署目录：`/home/appops/fanren-game`，8090 端口。
- `tools/hanli_face.py`、`hanli_hair.py`、`hanli_costume.py` 为组件；`tools/build_hanli.py` 统一组装、蒙皮、动作和导出。
- `FANREN_SKIP_RENDER=1 blender -b --factory-startup --python tools/build_hanli.py`
- 依次执行 `tools/validate-assets.mjs`、`tools/validate-model-polish.mjs`、`tools/validate-viewer.mjs`，通过后重新导入最终 GLB 渲染关键姿势。
- `./deploy.sh` 使用现有发布目录。同步前后核对 Git HEAD 与工作区，避免覆盖其他会话的新改动。

## 当前线上入口

- [韩立半身](http://23.82.99.226:8090/game3d.html?v=20261122-character5&view=hero&frame=portrait)
- [韩立头部](http://23.82.99.226:8090/game3d.html?v=20261122-character5&view=hero&frame=head)
- [3D 山门试炼](http://23.82.99.226:8090/game3d.html?v=20261122-character5)

下一阶段先补真实浏览器画面、CSS 和设备帧率验收，再继续面部、毛发与布料质量；本轮没有将这些未验收项标为通过。旧 reference-4 背面行走预览未纳入本轮发布。
