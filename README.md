# Photo Memory Video

一个“大学回忆视频生成器”MVP：从 YAML 配置读取照片、标题、时间和描述，自动排版，并用 MoviePy 生成温暖克制的 MP4 回忆视频。

## 安装

```bash
conda create -n photo-memory-video python=3.10 pip -y
conda activate photo-memory-video
python -m pip install -e .
```

需要系统可用的 FFmpeg。Windows 上如果已能运行 `ffmpeg -version`，通常就可以直接渲染。

## 快速运行

先生成示例照片：

```bash
python examples/create_demo_assets.py
```

再渲染示例视频：

```bash
photo-memory-video render --input examples/demo.yaml --output examples/output/demo.mp4
```

也可以直接使用模块入口：

```bash
python -m photo_memory_video render --input examples/demo.yaml --output examples/output/demo.mp4
```

## Web UI

启动本地编排界面：

```bash
photo-memory-video web --input examples/demo.yaml --output examples/output/demo.mp4
```

默认地址是：

```text
http://127.0.0.1:8765
```

界面支持：

- 编辑片名、分辨率、帧率、转场、淡入淡出
- 新增、删除、排序 scene
- 新增、删除、复制、排序照片
- 编辑照片路径、时间、标题和描述
- 通过系统文件选择器选择照片、照片目录和输出视频
- 从本地图片目录批量导入
- 按场景和自动分页预览画面
- 触发 MP4 渲染并显示进度

## 本地工作区

建议把自己的照片、编排配置和渲染结果放在 `workspace/`，这个目录不会进入 Git：

```text
workspace/
  photos/
  output/
  memory.yaml
```

启动针对本地工作区的 Web UI：

```bash
photo-memory-video web --input workspace/memory.yaml --output workspace/output/memory.mp4
```

## 配置格式

```yaml
video:
  title: "大学回忆"
  resolution: [1920, 1080]
  fps: 30
  transition_duration: 0.8
  fade_duration: 0.6

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

照片墙模式可以让单个场景更自由地错落排版：

```yaml
scenes:
  - title: "社团活动"
    layout: photo_wall
    wall:
      max_per_page: 6
      rotation: 8
      overlap: 0.16
    duration: 6
    photos:
      - path: "photos/001.jpg"
        caption: "第一次参加社团活动"
      - path: "photos/002.jpg"
        transform:
          x: 0.62
          y: 0.46
          width: 0.34
          rotation: 5
```

说明：

- `resolution` 默认是 `[1920, 1080]`。
- `fps` 默认是 `30`。
- `duration` 是 scene 时长，单位秒。
- `photos` 可以写单张图片路径，也可以写目录路径；目录会按文件名读取常见图片格式。
- 图片路径相对配置文件所在目录解析，不会修改原始图片。
- `layout: photo_wall` 会启用照片墙；`transform` 可选，用于微调单张照片的位置、宽度、旋转和适配方式。

## 开发验证

```bash
python -m pip install -e .[dev]
python -m pytest
```

当前 MVP 包含：

- YAML / JSON 配置读取与校验
- 单图、双图、三图、四图自动布局
- 五张及以上自动分页
- 中文字体探测、自动换行、半透明文字底
- Ken Burns 缓慢缩放和平移
- 柔和淡入淡出与跨页交叉淡化
- `photo-memory-video render` CLI
