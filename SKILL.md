---
name: douyin-github-video-pipeline
description: "Run the recurring Douyin pipeline for high-value GitHub projects: research and confirm a project plus angle, verify one real demo, prioritize user-recorded media, create narration and a template-rendered vertical video, verify the complete package, then use the user's logged-in Chrome to save a draft or schedule only with explicit authorization. Use for new episodes and interrupted-episode recovery; do not use for unrelated videos or immediate public posting."
---

# 抖音 GitHub 高价值项目视频流水线

把每期内容做成可恢复、低重复、可核验的流水线。默认工作区为用户当前打开的抖音技术视频目录；先读取该目录的 `AGENTS.md`，更近的项目规则优先。

## 开始方式

1. 查找现有 `episode.json`。存在时先读取它，只从记录的 `stage` 继续。
2. 没有状态文件时，先按 [项目筛选](references/project-selection.md) 工作；项目和角度确认后运行 `scripts/init_episode.py`。
3. 每完成一个阶段，用 `scripts/update_episode.py` 原子更新状态和产物路径。不要靠聊天记忆判断进度。
4. 每次只向用户提出一个清晰、必要的操作。

## 阶段路由

| 当前阶段 | 本阶段动作 | 按需读取 |
|---|---|---|
| `researching` / `awaiting_selection` | 筛选高价值项目，确认项目和视频角度 | [项目筛选](references/project-selection.md) |
| `selected` | 优先检查用户录屏/截图；不足时只补测一个核心功能 | [制作流程](references/production.md) |
| `demo_verified` / `script_ready` / `audio_ready` | 口播、剪映配音、字幕、模板化剪辑和封面 | [制作流程](references/production.md) |
| `rendered` | 机器检查、关键帧视觉检查和事实复核 | [成片验收](references/media-qa.md) |
| `qa_passed` / `uploading` | 读取最小发布载荷，在已登录 Chrome 中保存草稿或定时发布 | [浏览器交付](references/browser-delivery.md) |
| `needs_attention` | 核实外部状态后恢复，禁止盲目重试 | [恢复流程](references/recovery.md) |

状态字段和允许转换见 [episode 数据约定](references/episode-schema.md)。不要加载与当前阶段无关的 reference。

## 不变规则

- 推荐时同时锁定项目、真实痛点、唯一核心演示和前三秒结果。未经确认不安装、不写稿、不制作。
- Stars 只是热度信号；必须优先判断真实价值、账号匹配、去重、可演示性、Windows 门槛、费用、安全和维护状态。
- 候选阶段不安装所有项目。用户确认后只验证准备展示的一个核心功能。
- 用户真实录屏和截图优先。效果不足时才补充官方素材或由 Codex 自动实测、截图和录屏。
- 隐藏 API Key、Token、邮箱、账号、余额、私人路径、私有仓库、个人会话和系统通知。
- 配音默认使用剪映专业版“曼波讲故事”；以实际音频内容和时长为成片时间轴。剪映不可用时停止并报告，不擅自更换声音。
- 自动剪辑优先使用可复现的代码模板；若使用 HyperFrames，遵守其当前 skill 和 CLI 验证流程。不要每期用 GUI 重建完整时间线。
- `draft` 是默认交付模式。`schedule` 只有在用户确认准确账号、最终内容和发布时间后才可执行。永远不提供立即公开发布模式。
- 浏览器外部结果不确定时不得重复点击、删除、重发或覆盖。保存现有证据并转为 `needs_attention`。
- 同一种执行方式失败两次就停止该方式；检查原因后换一种方法，或保留进度并请求一个必要操作。

## 低 Token 纪律

- 官方事实、素材来源和实测证据只保存一次到 `episode.json` 与本期目录；只重验容易变化的版本、费用和发布状态。
- 重复的路径整理、状态更新、媒体探测、排期和发布载荷生成必须运行 `scripts/`，不手工重写。
- 脚本详细日志写入 `logs/`；聊天和标准输出只返回状态、失败字段与下一步。
- 浏览器阶段只读取 `publish/publish-payload.json`、当前账号和本 reference，不重新加载研究、口播和剪辑资料。
- 视觉检查只看开头、场景切换、字幕密集处、CTA和结尾等关键帧；发现问题后定点复查。

## 完成标准

只有以下结果全部成立才可报告完成：

- 最终竖屏 MP4 含口播音轨，音视频时长合理；
- 字幕、中文、中央安全区和结尾关注引导通过检查；
- 竖封面为 `1080x1920`，横封面为 `1440x1080`；
- 发布标题、介绍、话题、官方来源和必要费用说明齐全；
- 浏览器端明确核验为 `draft_saved` 或经授权后的 `scheduled`，不能用“已点击”替代结果证明。
