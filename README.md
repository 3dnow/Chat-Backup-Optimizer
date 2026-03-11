Chat Backup Optimizer / 聊天记录备份清理优化大师 🧹✨

English | 中文

<a id="english"></a> 🇬🇧 English

A blazing-fast, zero-dependency local *Chat chat history backup manager and deduplication tool.

If you use *Chat export tools to save your chat history as HTML files, you probably noticed that the media/ and files/ folders grow exponentially due to duplicated images and forwarded videos. Chat Backup Optimizer is designed to safely clean, manage, and heavily deduplicate these massive local backups without breaking your HTML chat links.

🌟 Key Features

🧠 Smart Orphaned-Media Deletion: Safely delete specific months of HTML chat logs. The tool uses Set Difference algorithms to calculate and delete only the orphaned media files, ensuring assets still referenced by other HTML files are never touched.

👯 Internal Deduplication: Forwarded the same video to 5 different groups? *Chat saves 5 physical copies. This tool finds internal duplicates, rewrites the HTML to point to a single master file, and deletes the redundant copies.

🔗 Cross-Archive Merging: Got an old backup on an external drive? Compare your current archive against the external one. The tool will delete local duplicates and rewrite your HTML src links using smart relative paths (e.g., ../../backup2/media/1.jpg), saving massive disk space without breaking the UI.

🚀 Blazing Fast "Double-Hash" Engine: Processing 50,000+ files? No problem. The tool uses a 3-tier filtration system: Size Clustering -> Fast Hash (64KB Head/Tail) -> Full MD5 Hash. It avoids full disk I/O, finishing in seconds what usually takes hours.

🛡️ Failsafe & Secure: Before any HTML link is rewritten, the original HTML is automatically backed up to a merge_back/ folder. Handles Windows "Read-Only" file permission errors automatically.

📦 Zero Dependencies: Built entirely with Python's standard library. No pip install required. Just run it.

🛠️ Installation & Usage

Prerequisites: Python 3.6+ installed on Windows.

Run: Double click chat_cleaner.py or run python chat_cleaner.py in your terminal.

Select Directory: Choose your *Chat backup root folder (must contain chat_*.html files and media/ / files/ subdirectories).

Choose an Action:

Select specific HTML files in the list and click "Secure Delete" to free up space from old chats.

Click "Internal Deduplicate" (Orange Button) to squeeze out space from duplicated memes and videos within the current folder.

Click "Merge with External Archive" (Blue Button) to link redundant files to a secondary backup drive.

<a id="chinese-中文"></a> 🇨🇳 中文

一款极速、零依赖的聊天记录本地备份管理与去重优化工具。

当你使用第三方工具将聊天记录导出为 HTML 格式时，你会发现 media/ 和 files/ 文件夹会因为群聊转发、重复发图而变得极其庞大。备份清理优化大师 专为解决此痛点而生，它能极其安全地清理、管理并对海量备份进行深度去重，且绝不损坏任何 HTML 聊天记录的图片展示。

🌟 核心特色

🧠 智能孤立媒体清理：想删掉某几个月的无用聊天记录？本工具基于“集合差集算法”，在删除 HTML 时，精确计算出仅被这些 HTML 引用的孤立媒体文件进行删除。绝不误删其他未删除聊天记录仍在引用的图片。

👯 存档内部极速去重：同一个搞笑视频发了 5 个群，本地硬盘就存了 5 份？一键内部去重！工具会自动将 HTML 里的链接全部重写指向唯一的“母文件”，并物理抹除其余多余副本，榨干最后一滴存储空间。

🔗 跨存档全局合并：如果你在移动硬盘里有一个旧的完整备份，你可以让当前备份与外部硬盘进行“对齐”。工具会删除当前盘的冗余文件，并使用精准的相对路径（如 ../../backup2/media/...）重写当前 HTML，让你在不占用本地空间的情况下，依然能丝滑查看聊天图片。

🚀 硬核的“双重哈希”预筛引擎：面对几万个媒体文件，传统 MD5 对比会卡死硬盘。本工具独创三级过滤：尺寸聚类预筛 -> 极速局部哈希（仅读头尾64KB） -> 全量 MD5 终极校验。完美避开 99% 的无效 I/O 读取，几十分钟的哈希对比压缩至十几秒内！

🛡️ 绝对安全的反悔机制：在执行任何去重和链接重写前，原版 HTML 文件会被完整移动到 merge_back/ 备份夹中。同时内置了强力属性解锁，完美解决导出的“只读文件”拒绝访问报错。

📦 零依赖，开箱即用：纯 Python 标准库编写（基于 tkinter）。无需繁琐的 pip install，双击即可运行，拥有极佳的跨设备兼容性。

🛠️ 安装与使用

环境准备：Windows 系统，并已安装 Python 3.6 或更高版本。

启动软件：双击 chat_cleaner.py 或在命令行执行 python chat_cleaner.py。

选择目录：点击左上角选择你的聊天记录导出根目录（该目录下需要有 chat_xxxx.html 文件以及 media 和 files 文件夹）。

执行优化操作：

安全删除：在中间的列表中选中想要丢弃的聊天记录（支持 Shift/Ctrl 多选），底部会实时算出真正的“可释放空间”，点击红色按钮安全删除。

当前目录内部去重（橘色按钮）：一键扫描当前文件夹里那些自己重复自己的图片/文件，重写链接并释放空间。

与外部存档去重合并（蓝色按钮）：选择另一个外部备份盘，将当前目录里与之重复的文件全部干掉，并用底层 os.path.relpath 生成跨盘/跨目录相对引用。

🔬 算法原理解析 (Under the Hood)

为什么它能这么快？
处理数万个甚至数百 GB 的视频/图片时，本工具采用了类似 P2P 软件的核心逻辑：

os.scandir 极速扫盘：摒弃缓慢的递归或常规 getsize。

尺寸聚类：大小不一样的文件，内容绝对不可能一样。将文件按字节大小分组，大小独一无二的文件直接放行。

极速指纹 (Fast Hash)：针对大小相同的文件，不读全量！仅读取文件的头部 64KB 和尾部 64KB 进行 MD5 碰撞。

全量确认 (Full Hash)：仅有极速指纹完全一致时，才会触发真正的全量 MD5 读取。配合正则回调替换（re.sub + urllib.parse），确保哪怕有中文路径名，也能毫秒级重写数以万计的 HTML 资源链接。

📄 License / 许可证

本项目采用 MIT License 开源，欢迎自由 Fork、修改和使用。如果这个工具帮你省下了几十 GB 的硬盘空间，欢迎给个 ⭐ Star！
