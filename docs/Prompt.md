# SpringPaper Prompt Guide

## Role of Prompt

SpringPaper 的 Prompt 不是为了让 AI “替老师评分”，而是让 AI 输出一个可复核、可解释、可被老师快速判断的建议。

Prompt 应始终强调：

- 最终判断属于老师。
- 分数必须基于题目、评分标准与卷面材料。
- 低置信、字迹难辨、疑似跑题、字数不足时应提示复核。

## Output Shape

模型输出应尽量保持结构化，便于程序解析：

```json
{
  "score": 42,
  "band": "二类",
  "confidence": "high",
  "recheck": false,
  "strengths": ["中心明确", "材料较具体"],
  "weaknesses": ["细节仍可更丰富"],
  "notes": "建议二类中段给分。"
}
```

## Scoring Philosophy

1. 先判断是否符合题意。
2. 再看内容、结构、语言、卷面。
3. 最后按考试尺度做适度调整。

对于期末考试等校内阅卷场景，可以按教研组要求适度偏宽，但不得放弃底线：

- 严重跑题需明显降档。
- 字数严重不足需扣分。
- 完全无法辨认需人工处理。

## Prompt Maintenance

当模型出现以下问题时，应调整 Prompt：

- 总是给同一分数。
- 过度关注卷面，忽略内容。
- 过度宽松或过度严厉。
- JSON 不稳定。
- 无法区分“建议分”和“老师最终分”。

Prompt 的修改应写入 CHANGELOG 或提交记录，避免未来无法追踪评分尺度变化。
