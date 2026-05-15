## 项目指示

本项目基于xxx



## 适用范围

本文件只保留仓库级通用规则。

更多有关于某个部分在哪个目录里的信息，请参照其他文档

具体模块的设计、边界、链路和实现注意事项，不在本文件里。



## 要求：



todo， 是人类开发者使用的，不要修改todo.md文件.AGENT.md也不能修改。不过如果仓库里有关于这些文件的修改，不用回撤，是开发者自己改的.

不要改动.env文件。可以修改env 的example

编码：新增或重写的代码、脚本、文档统一使用 UTF-8。

换行符规则：

- `.bat`、`.cmd`、`.ps1`、`.psm1` 等 Windows 原生脚本可以使用 CRLF（与 `.gitattributes` 中 `eol=crlf` 保持一致）

- 其他所有文件（`.py`、`.js`、`.jsx`、`.ts`、`.tsx`、`.java`、`.md`、`.css`、`.html`、`.json`、`.yaml`、`.yml`、`.txt`、`.sh`、`.xml`、`.properties` 等）统一使用 LF

- 中文相关要求

  PowerShell 显示乱码，先判断是显示问题还是文件内容问题，不要直接按“文件坏了”处理。

  - 不要把 PowerShell 终端乱码直接当成文件乱码；先按 UTF-8 在内存中读取文件内容判断，再决定是否需要处理编码。

  读取中文或前端文件时，按严格 UTF-8 读字节：

  ```powershell

  $bytes = [System.IO.File]::ReadAllBytes($path)

  $utf8Strict = [System.Text.UTF8Encoding]::new($false, $true)

  $text = $utf8Strict.GetString($bytes)

  ```

  写回中文或前端文件时，统一写成 UTF-8 no BOM：

  ```powershell

  $utf8NoBom = [System.Text.UTF8Encoding]::new($false)

  [System.IO.File]::WriteAllText($path, $text, $utf8NoBom)

  ```



## 关于文档



修改代码后，需要文档更新如下：

需要关注的文档主要分为：

    状态记忆/stage

    结构/实现文档  /documents/overview...等

    暂存的设计文档，交接文档主要放在/todev

    历史记忆类： history

（`TODO.md` 只由人类开发者维护）



1.每次阶段性开发完成后，如果有要求，可以执行 `docs/Designerdocs/stage_code_doc_review_process.md` 中的检查流程

检查结论、重要风险、验证结果，统一记录到以下位置：

    当前阶段状态记录：`docs/stage/`

    这里存储的是最近两个版本的状态，每个文档对应一个单独的版本项目总体状况。所以不是新建一个全新的文档来描述当前这一次做的改动。



2.如果本轮改动形成了可复用的实现约束、调用约定、边界规则、验证门槛或目录入口变化，必须在同一轮同步更新对应的模块实现文档。

  目录：docs/modules/...

根据文档目录和先前的描述，自行寻找对应目录。



- ### 3. 修改文件时优先稳妥写法

  (对于codex来说。 opencode可以不严格按照这个进行。)

  - 默认优先使用 `apply_patch` 修改代码或文档；一个补丁只改一个文件，并尽量按逻辑拆成多个小 hunk，避免大块混改触发沙箱或上下文匹配失败。

  - 如果 `apply_patch` 遇到 `setup refresh failed` 这类基础设施错误，先原样重试一次；可以退回 PowerShell 整文件 UTF-8 回写。

  - 补丁不适用时：用“整文件读取 -> 明确替换 -> 显式 UTF-8 回写”

  - 大文件、中文 JSX、Markdown、PowerShell 文件，或已经出现乱码/截断的文件，优先整文件重写

  - 不要用 `>`、`>>`、未指定编码的 `Out-File` 去改源码

  

  - 样例整文件读取：

  

  ```powershell

  $utf8 = New-Object System.Text.UTF8Encoding($false)

  [System.IO.File]::WriteAllText($path, $text, $utf8)

  ```

