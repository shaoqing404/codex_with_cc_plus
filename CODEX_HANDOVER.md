# CODEX HANDOVER CONTRACT: codex_with_cc_plus [COMPLETED]

> [!IMPORTANT]
> **致 Codex 主线程 / 代理 Leader：**
> 本项目已正式进行架构重构与物理迁移。
> 所有的后续开发及分发归属于全新的独立非 Fork 仓库：
> 👉 **[shaoqing404/codex_with_cc_plus](https://github.com/shaoqing404/codex_with_cc_plus)**
> 请仔细阅读本交接契约，并协助用户完成后续的文档优化与市场注册工作。

---

## 🛠️ Codex 核心任务指引

### 任务一：协助修改并在目标项目集成新版 README / AI_INSTALL
1. **路径与重定向核验**：
   - 检查 `README.md` 与 `AI_INSTALL.md` 中的所有 Git 连接、克隆地址及 Skill 路径，确保均已平移至新仓库 `shaoqing404/codex_with_cc_plus`。
2. **项目本地绑定**：
   - 当用户在你所管理的项目中输入：“请把本地 `~/.codex/skills/codex-with-cc` 子代理工作流绑定并应用到我当前的项目中”时，请自动识别本地手动拷贝的 Skill 模块并正确建立与 `.codex/` 路径的调用绑定。若 marketplace 已注册，则优先使用 marketplace 安装。

---

### 任务二：协助用户将插件注册到 Codex 市场

为方便后续其他项目通过一句话命令直接拉取安装，请你基于以下两种市场方案，编写自动化注册脚本或 PR 变更：

#### 选项 A：注册至公共市场 `aiskyhub/aiskyhub`
请生成或协助提交一个 Pull Request 到 `https://github.com/aiskyhub/aiskyhub`。
修改其 `.agents/plugins/marketplace.json` 中的 `codex-with-cc` 索引项为新仓库地址：
```json
{
  "name": "codex-with-cc",
  "description": "Codex with delegated Claude Code worker orchestration workflow",
  "version": "1.0.6",
  "repository": "https://github.com/shaoqing404/codex_with_cc_plus.git",
  "manifest": ".codex-plugin/plugin.json"
}
```

#### 选项 B：创建个人专属市场 `shaoqing404/marketplace`
若用户选择自建个人专属市场，请协助在本地或通过 GitHub CLI 执行以下操作：
1. 本地新建一个 `marketplace` 临时文件夹，在其中创建 `.agents/plugins/marketplace.json` 索引文件：
   ```json
   {
     "marketName": "shaoqing404",
     "plugins": {
       "codex-with-cc-plus@shaoqing404": {
         "name": "codex-with-cc-plus",
         "description": "Codex with delegated Claude Code worker orchestration workflow",
         "version": "1.0.6",
         "repository": "https://github.com/shaoqing404/codex_with_cc_plus.git",
         "manifest": ".codex-plugin/plugin.json"
       }
     }
   }
   ```
2. 使用 `gh repo create shaoqing404/marketplace --public --source=. --push` 自动将其发布为个人专属 Codex 市场，并引导用户使用以下命令：
   ```bash
   codex plugin marketplace add shaoqing404/marketplace
   /plugin install codex-with-cc-plus@shaoqing404 --scope user
   ```

---

## 🔍 终审与验收准则
- 所有的说明文档中无任何指向旧仓库的死链。
- 新增的 `.env` 环境变量配置指南能被用户和新安装实例正确读取。
- 本交接契约 `CODEX_HANDOVER.md` 已标记为 `[COMPLETED]`。
