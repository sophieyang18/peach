# 桃子 Application Copilot Extension

这是 Round 3A 的 Chrome Extension MVP，用于演示“桃子辅助填写网申”的主链路。

## 本地加载

1. 打开 Chrome：`chrome://extensions`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择本目录：`extension`
5. 启动 Peach 后端：`http://127.0.0.1:8000`
6. 打开 Demo ATS：`http://127.0.0.1:5173/demo-ats.html`
7. 点击浏览器右上角「桃子 Copilot」
8. 填入 Peach 用户名和后端地址
9. 点击「扫描」→「开始填写」
10. 用户在页面手动检查并提交后，回到 popup 点击「我已完成投递」

## 安全边界

- 不自动提交网申。
- 不填写 password / hidden / captcha / token 字段。
- 不把完整 HTML 发送到后端，只发送表单字段摘要。
- 低置信度字段不会自动填写。
- 开放题草稿必须由用户确认或编辑后才会写入页面。

## 当前 MVP 范围

支持：
- input / textarea / native select
- 姓名、手机、邮箱、学校、学历、专业、目标公司、目标岗位、实习描述、项目名称、项目描述、奖项、技能
- 开放题草稿生成
- 用户确认后写回 ApplicationState

暂不支持：
- 自定义 Select / Cascader / DatePicker
- 自动登录、验证码处理、自动 Submit
- 真实职位平台适配白名单
