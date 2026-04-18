# astrbot-plugin-whythemistake

AstrBot 插件：后台静默监听终端日志，检测到 WARNING / ERROR / CRITICAL 时自动提交 LLM 分析，将问题原因与解决方案（中文，≤50字）打印到终端。

## 功能

- 无需任何指令，插件激活后全程静默运行
- 拦截 loguru 的 WARNING 及以上级别日志（含完整 traceback）
- 相同报错自动去重，10 秒内多条报错只分析一次
- 分析结果以 `[WhyTheMistake] 错误分析: ...` 格式输出到终端

## 依赖

- AstrBot >= v4.5.0
- 已配置至少一个 LLM 提供商（在 AstrBot 管理面板中设置）

## 安装

在 AstrBot 插件管理页面搜索 `whythemistake` 安装，或手动将本目录放入 `data/plugins/`。

## 输出示例

```
[12:34:56] [Plug] [INFO] [main:127]: [WhyTheMistake] 错误分析: 原因：数据库连接超时。解决：检查数据库服务是否启动，确认连接配置正确。
```

## 配置说明

无需额外配置。插件使用 AstrBot 中当前第一个可用的 LLM 提供商进行分析。
