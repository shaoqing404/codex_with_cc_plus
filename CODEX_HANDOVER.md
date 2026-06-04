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

### 任务二：Codex 市场注册方式修正

本仓库已改为自带 Codex marketplace manifest，不需要 fork `aiskyhub/aiskyhub`，也不需要维护单独的 `shaoqing404/marketplace` 仓库。

主路径是把本仓库本身加入 Codex marketplace source：

```bash
codex plugin marketplace add shaoqing404/codex_with_cc_plus --ref master
codex plugin add codex-with-cc-plus@codex-with-cc-plus
```

仓库内的 `.agents/plugins/marketplace.json` 是 Codex marketplace 索引；`.codex-plugin/plugin.json` 是插件本体 manifest。

向 `aiskyhub/aiskyhub` 之类第三方公共市场提交 PR 只能作为“额外发现入口”，不是项目归属，也不是安装必需条件。`shaoqing404/aiskyhub` fork 不应作为 Codex With CC Plus 的维护仓库。

---

## 🔍 终审与验收准则
- 所有的说明文档中无任何指向旧仓库的死链。
- 新增的 `.env` 环境变量配置指南能被用户和新安装实例正确读取。
- 本交接契约 `CODEX_HANDOVER.md` 已标记为 `[COMPLETED]`。
