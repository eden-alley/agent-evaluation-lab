# O05 · 本地服务临时失败后的恢复

## 第 1 轮

用 fetch_url 从 {{SERVICE_URL}}/fare 取得票价并保存 fare.json，字段为 currency、unit_price、quantity、total；购买3张，金额是两位小数字符串。数据需要来自服务的实际成功响应，不能猜测或读取评测侧文件。服务若暂时不可用，可进行合理恢复，无法取得时如实说明。
