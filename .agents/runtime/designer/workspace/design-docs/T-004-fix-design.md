# T-004 Fix Design: AGENTS.md 引用验证脚本

## 问题
G3 验收失败：AGENTS.md Step 7 使用内联 bash 命令做安装验证，未引用 `scripts/verify-install.sh` 和 `scripts/verify-init.sh`。

## 修改方案

### 文件: `AGENTS.md`

在 Step 7 (验证安装结果) 之后，添加 **Step 7.1: 深度验证 (可选)**:

```markdown
### Step 7.1: 深度验证 (可选)
如果仓库中有验证脚本，可以运行完整验证：
\```bash
# 验证安装完整性（Skill 格式、YAML frontmatter、文件权限）
bash /tmp/multi-agent-framework/scripts/verify-install.sh

# 在项目初始化后，验证 .agents/ 目录结构
bash /tmp/multi-agent-framework/scripts/verify-init.sh
\```
> 注意：需要在 Step 6 清理之前运行，或者单独 clone 仓库。
```

### 替代方案（推荐）
将 Step 6 和 Step 7 的顺序调整 — 先验证再清理：

1. Step 6: 验证安装结果（保留现有内联检查）
2. Step 7: 深度验证（可选，引用脚本）
3. Step 8: 清理 `/tmp/multi-agent-framework`
4. Step 9: 输出结果

这样用户可以在清理前运行验证脚本。

## Implementer 注意事项
- 只改 AGENTS.md，不动其他文件
- 保持步骤编号连续
- 脚本路径使用 `/tmp/multi-agent-framework/scripts/`（安装流程中的临时目录）
