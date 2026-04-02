# Kiro.rs Admin API 自动同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Kiro 账号注册成功后，自动通过 kiro.rs 的 Admin API 推送兼容凭据，并支持对历史账号回填。

**Architecture:** 在后端新增一个独立的 `kiro.rs` 上传器，负责把本项目的 Kiro 账号转换为 kiro.rs 兼容 credential JSON，再映射成 Admin API 请求体并调用 `/api/admin/credentials`。现有 `services.external_sync` 与 `/integrations/backfill` 复用该上传器；配置项通过 `api/config.py` 和前端设置页暴露。

**Tech Stack:** FastAPI, SQLModel, requests, React + Ant Design

---

### Task 1: 先写失败验证，锁定上传器契约

**Files:**
- Create: `/tmp/test_kiro_rs_upload.py`
- Modify: 无
- Test: `/tmp/test_kiro_rs_upload.py`

- [ ] **Step 1: 写失败验证脚本**
- [ ] **Step 2: 运行并确认因为缺少上传器而失败**
- [ ] **Step 3: 以最小实现补足上传器接口**
- [ ] **Step 4: 重新运行并确认通过**

### Task 2: 接入自动同步与回填

**Files:**
- Create: `platforms/kiro/kiro_rs_upload.py`
- Modify: `services/external_sync.py`
- Modify: `api/integrations.py`

- [ ] **Step 1: 复用上传器接入注册成功后的自动同步**
- [ ] **Step 2: 复用上传器接入历史账号回填**
- [ ] **Step 3: 保持未配置时静默跳过，不影响主流程**

### Task 3: 暴露配置项

**Files:**
- Modify: `api/config.py`
- Modify: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: 新增后端配置白名单**
- [ ] **Step 2: 在设置页增加 kiro.rs Admin API 配置项**
- [ ] **Step 3: 保持 Kiro-only 前端结构不变**

### Task 4: 验证

**Files:**
- Modify: 无
- Test: `/tmp/test_kiro_rs_upload.py`

- [ ] **Step 1: 跑 Python 定向验证**
- [ ] **Step 2: 跑前端构建验证**
- [ ] **Step 3: 跑 Ruff / py_compile 做后端静态校验**
