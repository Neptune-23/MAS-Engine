# 公司 Vue 3 + JavaScript 开发绝对红线（第一版）

## 1. 技术栈铁律
- 前端框架必须使用 **Vue 3**，严禁使用 Vue 2。
- 编码语言必须使用 **JavaScript (ES6+)**，严禁强制使用 TypeScript（除非项目单独要求）。
- 状态管理必须使用 **Pinia**，严禁使用 Vuex。
- 路由必须使用 **Vue Router 4**。

## 2. 代码风格硬规定
- 所有 Vue 组件必须使用 **组合式 API (Composition API)** + `<script setup>` 语法糖。
- 组件命名必须采用 **多单词** 命名（例如 `UserProfile.vue`，严禁 `User.vue`）。
- Props 必须使用 `defineProps` 定义，并明确指定类型和默认值（例如 `defineProps({ title: { type: String, default: '' } })`）。
- 响应式数据必须使用 `ref` 或 `reactive`，严禁直接操作 `data()` 选项式写法。

## 3. 目录结构约束
- 页面级组件必须放在 `pages/` 下（按模块分文件夹）。
- 公共复用组件必须放在 `components/` 下。
- API 请求封装必须统一放在 `src/api/` 下，且文件名后缀必须为 `.js`。
- 工具函数必须放在 `src/utils/` 下。

## 4. 安全与质量红线
- 严禁在 `setup` 中直接暴露 `console.log` 到生产环境（必须使用 `import.meta.env.MODE` 判断）。
- 所有用户输入（`v-model`）在提交给后端前，必须进行前端格式校验。
- 所有 API 请求必须统一封装拦截器（Interceptor）处理 Token 和错误码。

## 5. Git 提交规范
- 提交信息必须遵循 `feat: xxx`、`fix: xxx`、`docs: xxx` 格式。

## 6. 项目结构必须与模板完全一致（HBuilder 兼容）

- `pages.json`、`manifest.json`、`App.vue`、`main.js` 必须保持在项目根目录（**不得移入 `src/` 子目录**），这是 HBuilderX 默认识别路径。
- 新增页面必须在 `pages.json` 的 `pages` 数组中正确注册，**不得手动修改 `pages.json` 的根结构**（只允许在 `pages` 数组尾部追加条目）。
- 静态资源必须放在 `static/` 目录，并通过 `/static/xxx` 引用（uni-app 规范）。
- 自定义组件必须放在 `components/` 或 `sheep/components/` 下，不得随意新建顶层目录。

## 7. 代码风格强制对齐模板（Prettier 配置）

- **所有 .vue / .js / .json 文件的缩进、引号、换行必须与模板根目录下的 `.prettierrc` 完全一致**。
- 模板根目录必须包含 `.prettierrc` 文件，其内容为：
  ```json
  {
    "printWidth": 100,
    "semi": true,
    "vueIndentScriptAndStyle": true,
    "singleQuote": true,
    "trailingComma": "all",
    "proseWrap": "never",
    "htmlWhitespaceSensitivity": "strict",
    "endOfLine": "auto"
  }

  ## 8. 禁止使用 HBuilderX 不支持的 ES 语法
  
  - 允许使用 ES6+ 常用特性（箭头函数、模板字符串、解构、`async/await`），**但禁止使用 ES2022 及以上的实验性特性**（如 `#` 私有字段、`Array.prototype.at()` 等），因为 HBuilderX 内置的编译环境可能无法转译。
  - 必须使用 `import` / `export` 模块语法，**禁止使用 `require` / `module.exports`**（uni-app 默认支持 ESM）。
  
  ## 9. API 请求必须走 `sheep.$api` 统一封装
  
  - 所有后端接口调用必须通过 `sheep.$api` 命名空间下的方法（如 `sheep.$api.user.list`），**不得直接使用 `uni.request` 或 `axios`**。
  - 若需要新增接口，必须在 `sheep/api/` 下按模块扩展，并遵循已有的命名和返回格式。
  
  ## 10. 新增页面必须同时更新 `pages.json` 和 `pages` 目录
  
  - 新建页面文件夹时，**必须同步在 `pages.json` 的 `pages` 数组中增加对应条目**（包括 `path` 和 `style`）。
  - 页面文件夹命名采用小写连字符（如 `user-center`），页面组件文件命名采用大驼峰（如 `UserCenter.vue`），**两者必须保持语义一致**。