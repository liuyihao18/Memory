# Photo Memory Video

> Produced by Codex.

大学回忆视频生成器：从 YAML / JSON 配置读取照片、标题、时间和描述，自动排版并用 MoviePy 生成温暖、克制、有纪念册气质的 MP4 视频。

项目目标不是做花哨模板，而是把照片、文字和时间感稳定地组织成可回看的影像。

## 功能概览

- YAML / JSON 配置读取
- 单图、多图、横竖图混排
- 1 至 4 张照片自动布局
- 5 张及以上自动分页
- `photo_wall` 照片墙布局，支持位置、宽度、旋转、层级、适配方式
- 中文文字渲染、自动换行、阴影和半透明文字底
- 场景级缓慢缩放，避免多张照片各自放大造成的不协调
- 柔和淡入淡出与跨页转场
- 全局 BGM，支持循环、音量和淡入淡出
- CLI 渲染 MP4
- Web UI 编排、预览、文件选择、渲染进度
- 照片墙图形编辑器，可拖动、缩放、旋转和调整层级
- 可关闭整页轻微缩放以获得静态纪念册效果

## 安装

推荐使用 conda：

```bash
conda create -n photo-memory-video python=3.10 pip -y
conda activate photo-memory-video
python -m pip install -e .
```

开发环境：

```bash
python -m pip install -e .[dev]
```

系统需要可用的 FFmpeg。Windows 上如果能运行下面命令，通常就可以正常渲染：

```bash
ffmpeg -version
```

## 快速开始

生成示例图片：

```bash
python examples/create_demo_assets.py
```

渲染示例视频：

```bash
photo-memory-video render --input examples/demo.yaml --output examples/output/demo.mp4
```

也可以使用模块入口：

```bash
python -m photo_memory_video render --input examples/demo.yaml --output examples/output/demo.mp4
```

只生成一张预览帧：

```bash
photo-memory-video render --input examples/demo.yaml --output examples/output/demo.mp4 --preview-frame examples/output/preview.png
```

## Web UI

启动本地编排界面：

```bash
photo-memory-video web --input examples/demo.yaml --output examples/output/demo.mp4
```

默认地址：

```text
http://127.0.0.1:8765
```

Web UI 支持：

- 编辑片名、分辨率、帧率、背景色、转场和淡入淡出
- 新增、删除、排序场景
- 新增、删除、复制、排序照片
- 编辑照片路径、时间、标题、描述
- 通过系统文件选择器选择照片、照片目录和输出视频
- 从本地图片目录批量导入
- 按场景和自动分页预览当前页
- 选择全局 BGM，并设置音量、循环、淡入和淡出
- 渲染 MP4 并显示进度条
- 保存当前配置到 YAML

### 照片墙图形编辑器

当场景使用 `layout: photo_wall` 时，可以点击右侧预览图或“图形编辑”按钮打开图形编辑器。

编辑器支持：

- 拖动照片卡片位置
- 拖动右下角控制点等比缩放
- 拖动顶部控制点旋转
- 置顶、置底
- 切换完整显示 / 裁切适配
- 点击“应用”后回填到当前页面的 `transform`

“应用”只更新当前 Web UI 状态；只有点击主界面的“保存”按钮后，才会写入 YAML。

非照片墙场景打开图形编辑器时会显示提示，并可一键切换为照片墙布局。

## 本地工作区

建议把自己的照片、配置和输出放在 `workspace/`，这个目录默认不会进入 Git：

```text
workspace/
  photos/
  output/
  memory.yaml
```

启动针对工作区的 Web UI：

```bash
photo-memory-video web --input workspace/memory.yaml --output workspace/output/memory.mp4
```

## 配置格式

基础示例：

```yaml
video:
  title: "大学回忆"
  resolution: [1920, 1080]
  fps: 30
  transition_duration: 0.8
  fade_duration: 0.6
  scene_zoom: true
  audio:
    path: "music/bgm.mp3"
    volume: 0.35
    fade_in: 1.0
    fade_out: 2.0
    loop: true

scenes:
  - title: "大一"
    description: "故事从这里慢慢开始。"
    duration: 6
    photos:
      - path: "photos/001.jpg"
        time: "2022.09"
        caption: "第一次班会"
        description: "那时候大家都还不熟。"
      - path: "photos/002.jpg"
        caption: "第一次聚餐"
```

照片墙示例：

```yaml
scenes:
  - title: "社团活动"
    layout: photo_wall
    wall:
      max_per_page: 6
      rotation: 8
      overlap: 0.16
      card_width: 0.32
      spread: 1.1
      caption_safe: true
      randomness: 0.6
      random_seed: 202405
      style: print
    duration: 6
    photos:
      - path: "photos/001.jpg"
        caption: "第一次参加社团活动"
      - path: "photos/002.jpg"
        time: "2023.04"
        caption: "操场边的傍晚"
        transform:
          x: 0.62
          y: 0.46
          width: 0.34
          rotation: 5
          fit: contain
          z_index: 1
```

字段说明：

- `resolution` 默认是 `[1920, 1080]`
- `fps` 默认是 `30`
- `duration` 是 scene 时长，单位秒
- `scene_zoom` 控制整页轻微缩放，默认 `true`
- `video.audio.path` 配置全局 BGM，路径相对配置文件所在目录解析；留空则不写入音频
- `video.audio.volume` 控制 BGM 音量，范围 `0` 到 `2`，默认 `0.35`
- `video.audio.fade_in` / `video.audio.fade_out` 控制 BGM 淡入淡出秒数，默认 `1.0` / `2.0`
- `video.audio.loop` 默认 `true`，短音频会循环到视频总时长，长音频会裁剪到视频总时长
- `photos` 可以写单张图片路径，也可以写目录路径
- 图片路径相对配置文件所在目录解析
- 程序不会修改原始图片
- `layout` 支持 `auto`、`grid`、`photo_wall`
- `wall.max_per_page` 控制照片墙每页最多照片数，最大为 9
- `wall.rotation` 控制自动照片墙旋转强度
- `wall.overlap` 控制自动照片墙错落重叠感
- `wall.card_width` 控制照片墙默认卡片宽度，单位是画布宽度比例；留空则使用自动宽度
- `wall.spread` 控制照片墙分散程度，默认 `1.0`
- `wall.caption_safe` 默认 `true`，自动重排时尽量减少其他卡片遮挡照片 caption/time
- `wall.randomness` 控制自动重排的随机偏移强度，默认 `0`
- `wall.random_seed` 控制随机排布结果；同一种子会稳定复现，Web UI 的“随机重排”会自动换一个新种子
- `wall.style` 支持 `print` 和 `clean`
- 照片墙卡片内部照片保持静态取景，整体页面会做统一的轻微缩放
- Web UI 的“按当前宽度重排”会保留已有 `transform.width`、`transform.height` 和 `transform.fit`，只重新计算位置、旋转和层级；“随机重排”会保留当前宽度并更新随机种子
- `transform.x`、`transform.y` 是照片卡片中心点的归一化坐标
- `transform.width` 是卡片宽度占画布宽度的比例
- `transform.rotation` 范围是 `-45` 到 `45`
- `transform.fit` 支持 `contain` 和 `cover`
- `transform.z_index` 控制照片墙层级

## 开发验证

```bash
python -m pytest
node --check src/photo_memory_video/web_static/app.js
```

如果修改了 Web UI，建议用 `examples/demo.yaml` 和 `examples/photos` 做视觉验证，避免误用私人照片。

## 项目结构

```text
src/photo_memory_video/
  cli.py
  config_loader.py
  layout.py
  render.py
  text_renderer.py
  timeline.py
  transitions.py
  web.py
  web_state.py
  web_static/
```
