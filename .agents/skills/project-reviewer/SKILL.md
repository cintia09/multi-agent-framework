---
name: project-reviewer
description: "本项目的审查标准和代码质量要求。审查者 agent 工作时加载。"
---

# 项目级审查指南

## 审查清单
- [ ] 测试通过: `bash tests/run-all.sh`
- [ ] SKILL.md 有 YAML frontmatter (`name` + `description`)
- [ ] Hook 脚本有 `+x` 权限
- [ ] JSON 文件格式合法 (python3 -m json.tool)
- [ ] 无硬编码绝对路径 (使用相对路径或 `$HOME`)
- [ ] 无安全漏洞 (硬编码密钥、未转义的用户输入)
- [ ] Commit message 英文
- [ ] 新增功能有对应 goal 描述
- [ ] 不破坏现有 skill 内容 (只追加/增强)

## 项目特有规则
- 所有 SKILL.md 必须保持向后兼容 (不删除已有 section)
- FSM 状态转换: 修改 agent-fsm/SKILL.md 需额外审查转换表完整性
- Task Board: 修改 task-board.json 需验证 version 字段递增
- Memory: 修改 agent-memory/SKILL.md 需确保 capture/load 对称

## 严重级别判定
| 级别 | 描述 | 示例 |
|------|------|------|
| CRITICAL | 破坏核心流程 | FSM 转换表缺失状态, task-board 结构错误 |
| HIGH | 功能缺失 | Skill 缺少必要 section, hook 缺少权限 |
| MEDIUM | 质量问题 | 文档不清晰, 路径硬编码 |
| LOW | 风格建议 | 命名不一致, 格式微调 |

## 审查报告模板
输出到 `.agents/runtime/reviewer/workspace/review-reports/review-T-NNN-<date>.md`:
- **严重问题** (必须修复)
- **建议** (可选修复)
- **总评**: PASS / FAIL (CRITICAL/HIGH 存在则 FAIL)
