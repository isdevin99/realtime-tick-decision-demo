# 实时逐笔判断：最小 Python 示例

这是一个独立、离线可运行的教学项目，演示如何把**规范化逐笔成交记录**转换成透明、可解释的观察结果。

它不会连接任何行情服务器，不会发送订单，也不构成投资建议。示例数据全部为合成数据。

## 示例做什么

1. 读取每行一条 JSON 的逐笔成交。
2. 校验股票代码、交易时间、成交价、股数、成交额和方向。
3. 按每只股票的 5 秒区间聚合主动买入额和主动卖出额。
4. 仅将 `B`（主动买）与 `S`（主动卖）计入方向净额；`C`（撤单）和 `N`（中性/方向不明）不参与方向计算。
5. 一个 5 秒区间由下一条更晚区间的数据关闭；文件结束时显式关闭最后一个未完成区间。
6. 当买卖净额达到用户给定阈值时输出观察事件和可读原因。输出只是规则示例，不是买卖指令。

## 运行

只需要 Python 3.10+ 标准库；测试需要 pytest。无需安装行情 SDK 或连接上游。

```bash
python -m tickdemo examples/synthetic_ticks.jsonl --threshold-yuan 20000
```

每个输出事件为一行 JSON，例如：

```json
{"ts_code":"000001.SZ","bucket_start":"09:30:00.000","bucket_end":"09:30:04.999","buy_yuan":"60000","sell_yuan":"25025","net_yuan":"34975","tick_count":2,"status":"observe_buy_pressure","reason":"buy-sell net 34975 >= threshold 20000 yuan"}
```

执行测试：

```bash
python -m pytest -q
```

## 输入字段

输入为 UTF-8 JSONL，每行是一条已经解码且归一化的成交记录：

| 字段 | 类型 | 含义 |
|---|---|---|
| `ts_code` | string | 证券代码，例如 `000001.SZ` |
| `time` | string | 交易所时间，`HH:MM:SS.mmm` |
| `price` | decimal/string | 元/股 |
| `volume` | integer | 股 |
| `turnover` | decimal/string | 元 |
| `bs_flag` | string | `B` 主动买，`S` 主动卖，`C` 撤单，`N` 中性或方向不明 |

### 重要边界

- 缺少成交量、成交额或方向时，示例拒绝该记录，不会根据价格变化虚构买卖方向。
- 撤单和中性成交不会进入买卖净额。
- 跨 5 秒区间时，先关闭旧区间，再加入当前记录。
- 不规则序号、缺失时间段不会补成零成交。
- 生产接入时必须依照数据提供方正式授权的接口说明，先验证账户实际收到的字段；不要把行情快照误当作逐笔成交。
- 证券代码与示例记录均为虚构或通用格式演示；本仓库没有真实客户数据、凭证或内部平台代码。

## 目录

- `tickdemo/engine.py`：字段验证、5 秒聚合和观察规则。
- `tickdemo/__main__.py`：命令行入口。
- `examples/synthetic_ticks.jsonl`：合成逐笔样例。
- `tests/test_engine.py`：离线单元测试。

## License

MIT；见 `LICENSE`。
