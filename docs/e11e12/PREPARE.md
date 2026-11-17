# 生成 E11–E12 提交文档

在服务器 A-buildchecker 的 e11-e12-integration 分支执行：

```bash
python3 scripts/prepare_e11e12_submission.py
```

脚本读取已经完成的 work/e11-a-01、work/e11-a-02、work/e11-stale-01、work/e12-02、
work/api-client、work/e12-real-review.json，核对状态和哈希后再生成文档。
新工具 CI 记录使用已核验的 run 44103198658，不将其混作集成仓库的 CI。

主要产物：

- docs/个人报告.md
- docs/ADR.md
- docs/接口契约.md（保留原文并补扩展入口）
- docs/e11e12/README.md
- docs/e11e12/数据与联调记录.csv
- docs/e11e12/PR_BODY.md

原文备份与生成收据保存在 work/。已填写的自定义文档不会被当作空模板覆盖；
根报告有自填内容时脚本会提示人工合并，重复目录中的自填内容则原样保留。
后续 PR/CI 的实际 run、head SHA 和结论需在 CI 阶段取证保存，并在报告状态中更新。
