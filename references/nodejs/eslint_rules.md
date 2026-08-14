# Node.js 开发规则

## 1. 代码风格
- 使用 ESLint 作为代码规范工具
- 推荐使用 Airbnb 或 Standard 风格
- 使用 Prettier 自动格式化

## 2. 包管理
- 使用 npm 或 yarn 管理依赖
- 锁定依赖版本（`package-lock.json` 或 `yarn.lock`）
- 区分 dependencies 和 devDependencies

## 3. 错误处理
- 使用 try-catch 捕获异步错误
- 使用 .catch() 处理 Promise 错误
- 错误信息应包含足够的上下文

## 4. 模块规范
- 使用 ES6 模块语法（import/export）
- 禁止使用 require/module.exports（除非特殊场景）
- 按功能划分模块

## 5. 测试
- 使用 Jest、Mocha 或 Vitest 编写测试
- 测试覆盖核心功能
- 测试文件命名：`*.test.js` 或 `*.spec.js`

## 6. 环境配置
- 敏感信息通过 .env 管理
- 使用 dotenv 加载环境变量
- 区分开发环境和生产环境配置
