# astrbot-plugin-whythemistake

AstrBot 插件：后台静默监听终端日志，检测到 WARNING / ERROR / CRITICAL 时自动提交 LLM 分析，将问题原因与解决方案（中文，≤50字）打印到终端。

## 功能

- 无需任何指令，插件激活后全程静默运行
- 通过标准 `logging.Handler` 挂载到 `astrbot` 日志器，捕获 WARNING 及以上级别（含完整 traceback）
- 相同报错 FIFO 去重（最多缓存 200 条），10 秒内多条报错只分析一次
- 分析结果以 `[WhyTheMistake] 错误分析: ...` 格式输出到终端

## 依赖

- AstrBot >= v4.5.0
- 已配置至少一个 LLM 提供商（在 AstrBot 管理面板中设置）
- 无额外第三方依赖

## 安装

在 AstrBot 插件管理页面搜索 `whythemistake` 安装，或手动将本目录放入 `data/plugins/`。

## 输出示例

```
[12:34:56] [Plug] [INFO] [main:88]: [WhyTheMistake] 错误分析: 原因：数据库连接超时。解决：检查数据库服务是否启动，确认连接配置正确。
```
