# episode.json 数据约定

`episode.json` 是每期唯一真源。所有路径使用绝对路径，写入采用 UTF-8 与原子替换。

## 阶段

```text
researching
awaiting_selection
selected
demo_verified
script_ready
audio_ready
rendered
qa_passed
uploading
draft_saved
scheduled
needs_attention
```

正常转换由 `scripts/update_episode.py` 验证。发生阻塞时转为 `needs_attention`，脚本保存 `blocked_from`；处理完后使用 `--resume` 返回原阶段。

## 关键字段

- `project`：名称、仓库、版本和视频角度。
- `research`：官方来源、核实时间、费用核实和核心演示证据。
- `artifacts`：脚本、配音、转录、最终视频、两种封面和发布信息绝对路径。
- `publish`：模式、标题、介绍、话题、定时时间和定时授权。
- `qa`：通过状态、报告路径和检查时间。
- `browser`：目标账号、浏览器状态和核验证据。
- `history`：阶段变更、原因和时间；不要删除旧记录。

## 定时授权

定时模式先生成未授权 payload 预览。把最终摘要交给用户确认后，才能把下列字段写入状态：

```json
{
  "publish": {
    "schedule_confirmation": {
      "confirmed": true,
      "confirmed_at": "ISO-8601时间",
      "payload_fingerprint": "脚本生成的sha256"
    }
  }
}
```

Agent不得根据以前的确认、相似标题或Skill的存在自行设置这些字段。payload变化后指纹失效，必须重新确认。
