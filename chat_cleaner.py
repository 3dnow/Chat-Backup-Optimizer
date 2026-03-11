import os
import re
import glob
import threading
import urllib.parse
import hashlib
import shutil
import stat
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

class ChatBackupCleaner:
    def __init__(self, root):
        self.root = root
        self.root.title("聊天记录备份管理工具")
        self.root.geometry("900x650")
        self.root.minsize(800, 600)
        
        # 数据存储结构
        self.base_dir = ""
        self.html_files = {}       # { filepath: { 'start': str, 'end': str, 'size': int, 'assets': set() } }
        self.asset_sizes = {}      # { asset_rel_path: size_in_bytes }
        
        # UI 初始化
        self.setup_ui()

    def setup_ui(self):
        # 字体设置
        default_font = ("Microsoft YaHei", 10)
        
        # === 顶部区域：目录选择 ===
        top_frame = tk.Frame(self.root, pady=10, padx=10)
        top_frame.pack(fill=tk.X)
        
        tk.Label(top_frame, text="备份目录: ", font=default_font).pack(side=tk.LEFT)
        self.dir_entry = tk.Entry(top_frame, width=60, font=default_font, state='readonly')
        self.dir_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="选择目录并扫描", command=self.select_directory, font=default_font, bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=5)
        
        tk.Button(top_frame, text="与外部存档去重合并", command=self.start_dedup_process, font=default_font, bg="#2196F3", fg="white").pack(side=tk.RIGHT, padx=5)
        
        # 新增内部去重按钮
        tk.Button(top_frame, text="当前目录内部去重", command=self.start_internal_dedup_process, font=default_font, bg="#FF9800", fg="white").pack(side=tk.RIGHT, padx=5)
        
        # === 信息统计区域 ===
        stats_frame = tk.LabelFrame(self.root, text="全局空间统计", font=default_font, pady=10, padx=10)
        stats_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.lbl_total_html = tk.Label(stats_frame, text="HTML文件数: 0", width=20, anchor='w')
        self.lbl_total_html.grid(row=0, column=0, padx=5, pady=2)
        
        self.lbl_size_html = tk.Label(stats_frame, text="HTML总大小: 0 B", width=20, anchor='w')
        self.lbl_size_html.grid(row=0, column=1, padx=5, pady=2)
        
        self.lbl_size_media = tk.Label(stats_frame, text="Media大小: 0 B", width=20, anchor='w')
        self.lbl_size_media.grid(row=1, column=0, padx=5, pady=2)
        
        self.lbl_size_files = tk.Label(stats_frame, text="Files大小: 0 B", width=20, anchor='w')
        self.lbl_size_files.grid(row=1, column=1, padx=5, pady=2)
        
        # === 进度条 ===
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(stats_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=2, column=0, columnspan=4, sticky="ew", pady=10)
        self.lbl_status = tk.Label(stats_frame, text="等待操作...", fg="gray")
        self.lbl_status.grid(row=3, column=0, columnspan=4, sticky="w")
        
        # === 中间区域：文件列表 ===
        list_frame = tk.Frame(self.root, padx=10, pady=5)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # 列表过滤与操作按钮
        filter_frame = tk.Frame(list_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        tk.Label(filter_frame, text="选择要删除的记录 (支持Ctrl/Shift多选):", font=("Microsoft YaHei", 10, "bold")).pack(side=tk.LEFT)
        
        self.btn_compare = tk.Button(filter_frame, text="与外部文件对比", command=self.compare_with_external_html, state=tk.DISABLED)
        self.btn_compare.pack(side=tk.LEFT, padx=10)
        
        tk.Button(filter_frame, text="全选", command=self.select_all).pack(side=tk.RIGHT, padx=2)
        tk.Button(filter_frame, text="取消全选", command=self.deselect_all).pack(side=tk.RIGHT, padx=2)
        
        # Treeview
        columns = ("filename", "start_date", "end_date", "html_size", "asset_count")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("filename", text="文件名")
        self.tree.heading("start_date", text="开始日期")
        self.tree.heading("end_date", text="结束日期")
        self.tree.heading("html_size", text="HTML大小")
        self.tree.heading("asset_count", text="关联媒体/文件数")
        
        self.tree.column("filename", width=250)
        self.tree.column("start_date", width=100, anchor='center')
        self.tree.column("end_date", width=100, anchor='center')
        self.tree.column("html_size", width=100, anchor='e')
        self.tree.column("asset_count", width=120, anchor='center')
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定选择事件
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        
        # === 底部区域：删除操作 ===
        bottom_frame = tk.LabelFrame(self.root, text="清理操作", font=default_font, pady=10, padx=10)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.lbl_selected_info = tk.Label(bottom_frame, text="已选 HTML: 0 个 | 预计释放空间: 0 B", font=("Microsoft YaHei", 10, "bold"), fg="#D32F2F")
        self.lbl_selected_info.pack(side=tk.LEFT, padx=10)
        
        self.btn_delete = tk.Button(bottom_frame, text="安全删除选中记录", command=self.execute_deletion, font=default_font, bg="#F44336", fg="white", state=tk.DISABLED)
        self.btn_delete.pack(side=tk.RIGHT, padx=10)

    def format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = 0
        while size_bytes >= 1024 and i < len(size_name) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.2f} {size_name[i]}"

    def select_directory(self):
        dir_path = filedialog.askdirectory(title="选择聊天记录备份根目录 (包含 chat_*.html 和 media/ files/ 目录)")
        if not dir_path:
            return
            
        self.dir_entry.config(state='normal')
        self.dir_entry.delete(0, tk.END)
        self.dir_entry.insert(0, dir_path)
        self.dir_entry.config(state='readonly')
        self.base_dir = dir_path
        
        # 启动扫描线程
        threading.Thread(target=self.scan_directory_thread, daemon=True).start()

    def _get_dir_size_fast(self, folder_name):
        # 极速获取目录总大小，使用底层 os.scandir 避免常规 os.path.getsize 的高昂系统调用开销
        total_size = 0
        dir_path = os.path.join(self.base_dir, folder_name)
        if os.path.exists(dir_path):
            try:
                for entry in os.scandir(dir_path):
                    if entry.is_file():
                        total_size += entry.stat().st_size
            except Exception:
                pass
        return total_size

    def scan_directory_thread(self):
        self.root.after(0, lambda: self.set_ui_state('scanning'))
        self.html_files.clear()
        self.asset_sizes.clear()
        
        try:
            # 1. 查找所有 HTML 文件
            pattern = os.path.join(self.base_dir, "chat_*_*_*.html")
            files = glob.glob(pattern)
            total_files = len(files)
            
            if total_files == 0:
                self.root.after(0, lambda: messagebox.showwarning("提示", "该目录下未找到符合格式的 chat_*.html 文件！"))
                self.root.after(0, lambda: self.set_ui_state('normal'))
                return

            # 解析正则模式
            img_re = re.compile(r'src=["\'](media/[^"\']+)["\']')
            video_re = re.compile(r'loadVideo\s*\(\s*this\s*,\s*["\'](media/[^"\']+)["\']\s*\)')
            audio_re = re.compile(r'<audio[^>]+src=["\'](media/[^"\']+)["\']')
            file_re = re.compile(r'href=["\'](files/[^"\']+)["\']')

            total_html_size = 0
            
            # 2. 遍历解析所有 HTML 文件
            for i, filepath in enumerate(files):
                filename = os.path.basename(filepath)
                
                # 提取日期 chat_20200503_20200602_12.html
                match = re.search(r'chat_(\d{8})_(\d{8})_(\d+)\.html', filename)
                start_date = match.group(1) if match else "未知"
                end_date = match.group(2) if match else "未知"
                
                html_size = os.path.getsize(filepath)
                total_html_size += html_size
                
                assets = set()
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                    # 查找所有引用
                    assets.update(img_re.findall(content))
                    assets.update(video_re.findall(content))
                    assets.update(audio_re.findall(content))
                    assets.update(file_re.findall(content))
                
                # 处理 URL 编码 (解决中文名问题) 并规范化路径
                decoded_assets = {urllib.parse.unquote(a) for a in assets}
                
                self.html_files[filepath] = {
                    'filename': filename,
                    'start_date': start_date,
                    'end_date': end_date,
                    'size': html_size,
                    'assets': decoded_assets
                }
                
                # 更新进度
                progress = int((i + 1) / total_files * 80) # 扫描占80%进度
                self.root.after(0, lambda p=progress, fn=filename: self.update_progress(p, f"正在分析: {fn}"))

            # 3. 使用极速方式统计全局媒体和文件大小 (通过 os.scandir)
            self.root.after(0, lambda: self.update_progress(85, "正在极速计算媒体和文件物理大小..."))
            total_media_size = self._get_dir_size_fast("media")
            total_files_size = self._get_dir_size_fast("files")

            # 4. 更新 UI 树状列表和统计面板
            self.root.after(0, lambda: self.populate_tree())
            self.root.after(0, lambda: self.lbl_total_html.config(text=f"HTML文件数: {len(self.html_files)}"))
            self.root.after(0, lambda: self.lbl_size_html.config(text=f"HTML总大小: {self.format_size(total_html_size)}"))
            self.root.after(0, lambda: self.lbl_size_media.config(text=f"Media总大小: {self.format_size(total_media_size)}"))
            self.root.after(0, lambda: self.lbl_size_files.config(text=f"Files总大小: {self.format_size(total_files_size)}"))
            self.root.after(0, lambda: self.update_progress(100, "扫描完成！请选择要删除的记录。"))
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"扫描过程中发生错误: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.set_ui_state('normal'))

    def populate_tree(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        # 按开始日期排序
        sorted_files = sorted(self.html_files.items(), key=lambda x: x[1]['start_date'])
        
        for filepath, data in sorted_files:
            self.tree.insert("", tk.END, iid=filepath, values=(
                data['filename'],
                data['start_date'],
                data['end_date'],
                self.format_size(data['size']),
                len(data['assets'])
            ))

    def on_tree_select(self, event):
        selected_items = self.tree.selection()
        if not selected_items:
            self.lbl_selected_info.config(text="已选 HTML: 0 个 | 预计释放空间: 0 B")
            self.btn_delete.config(state=tk.DISABLED)
            self.btn_compare.config(state=tk.DISABLED)
            return

        self.btn_delete.config(state=tk.NORMAL)
        # 对比按钮仅在单选时可用
        if len(selected_items) == 1:
            self.btn_compare.config(state=tk.NORMAL)
        else:
            self.btn_compare.config(state=tk.DISABLED)

        # 使用线程计算释放空间，避免选中大量文件时卡顿
        threading.Thread(target=self.calculate_freed_space_thread, args=(selected_items,), daemon=True).start()

    def calculate_freed_space_thread(self, selected_filepaths):
        self.root.after(0, lambda: self.lbl_selected_info.config(text="正在计算预计释放空间..."))
        self.root.after(0, lambda: self.btn_delete.config(state=tk.DISABLED))
        
        selected_set = set(selected_filepaths)
        
        # 1. 计算要删除的 HTML 释放的空间
        html_freed_size = sum(self.html_files[fp]['size'] for fp in selected_set)
        
        # 2. 收集【选中文件】引用的资产
        assets_in_selected = set()
        for fp in selected_set:
            assets_in_selected.update(self.html_files[fp]['assets'])
            
        # 3. 收集【未被选中（保留）文件】引用的资产
        assets_in_kept = set()
        for fp, data in self.html_files.items():
            if fp not in selected_set:
                assets_in_kept.update(data['assets'])
                
        # 4. 核心逻辑：真正可以删除的资产 = 选中文件引用的资产 - 保留文件引用的资产 (差集)
        assets_to_delete = assets_in_selected - assets_in_kept
        
        # 5. 按需计算这些可删除资产的大小 (加入缓存机制和进度指示防假死)
        assets_freed_size = 0
        total_assets = len(assets_to_delete)
        
        for i, asset in enumerate(assets_to_delete):
            if asset not in self.asset_sizes:
                abs_path = os.path.join(self.base_dir, os.path.normpath(asset))
                try:
                    self.asset_sizes[asset] = os.path.getsize(abs_path)
                except Exception:
                    self.asset_sizes[asset] = 0
            
            assets_freed_size += self.asset_sizes[asset]
            
            # 刷新UI文本显示进度
            if i % 100 == 0:
                self.root.after(0, lambda p=i, t=total_assets: self.lbl_selected_info.config(text=f"正在分析文件大小 ({p}/{t})..."))
        
        total_freed = html_freed_size + assets_freed_size
        
        info_text = f"已选 HTML: {len(selected_set)} 个 | 孤立媒体文件数: {len(assets_to_delete)} 个 | 预计总释放空间: {self.format_size(total_freed)}"
        self.root.after(0, lambda: self.lbl_selected_info.config(text=info_text))
        self.root.after(0, lambda: self.btn_delete.config(state=tk.NORMAL))
        
        # 保存将要删除的资产清单，供执行删除时使用
        self.current_assets_to_delete = assets_to_delete

    def execute_deletion(self):
        selected_filepaths = self.tree.selection()
        if not selected_filepaths:
            return
            
        confirm = messagebox.askyesno("警告", 
            f"您确定要永久删除这 {len(selected_filepaths)} 个 HTML 文件及其相关的孤立媒体文件吗？\n"
            "操作不可逆，请确保您已了解后果！")
            
        if not confirm:
            return
            
        threading.Thread(target=self.delete_thread, args=(selected_filepaths, self.current_assets_to_delete), daemon=True).start()

    def delete_thread(self, html_to_delete, assets_to_delete):
        self.root.after(0, lambda: self.set_ui_state('deleting'))
        
        deleted_size_bytes = 0
        deleted_html_count = 0
        deleted_asset_count = 0
        
        total_ops = len(html_to_delete) + len(assets_to_delete)
        current_op = 0
        
        try:
            # 1. 删除孤立的资产文件 (media 和 files)
            for asset_rel_path in assets_to_delete:
                abs_path = os.path.join(self.base_dir, os.path.normpath(asset_rel_path))
                if os.path.exists(abs_path):
                    size = os.path.getsize(abs_path)
                    os.chmod(abs_path, stat.S_IWRITE)  # 强制移除只读属性
                    os.remove(abs_path)
                    deleted_size_bytes += size
                deleted_asset_count += 1
                
                current_op += 1
                if current_op % 50 == 0:
                    prog = int((current_op / total_ops) * 100)
                    self.root.after(0, lambda p=prog: self.update_progress(p, f"正在清理相关媒体/文件... ({current_op}/{total_ops})"))

            # 2. 删除 HTML 文件
            for fp in html_to_delete:
                if os.path.exists(fp):
                    size = os.path.getsize(fp)
                    os.chmod(fp, stat.S_IWRITE)  # 强制移除只读属性
                    os.remove(fp)
                    deleted_size_bytes += size
                
                # 从内存记录中移除
                if fp in self.html_files:
                    del self.html_files[fp]
                    
                deleted_html_count += 1
                current_op += 1
                prog = int((current_op / total_ops) * 100)
                self.root.after(0, lambda p=prog: self.update_progress(p, f"正在删除 HTML 记录... ({current_op}/{total_ops})"))
                
            self.root.after(0, lambda: messagebox.showinfo("清理完成", 
                f"成功删除 HTML文件 {deleted_html_count} 个\n"
                f"成功删除 媒体文件 {deleted_asset_count} 个\n"
                f"共为您释放空间: {self.format_size(deleted_size_bytes)}"))
                
            # 重新扫描更新状态
            self.root.after(0, self.scan_directory_thread)

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"删除过程中发生异常: {str(e)}"))
            self.root.after(0, lambda: self.set_ui_state('normal'))

    def select_all(self):
        self.tree.selection_set(self.tree.get_children())
        
    def deselect_all(self):
        self.tree.selection_remove(self.tree.selection())

    def update_progress(self, value, text):
        self.progress_var.set(value)
        self.lbl_status.config(text=text)

    def set_ui_state(self, state):
        if state == 'scanning' or state == 'deleting':
            self.btn_delete.config(state=tk.DISABLED)
            self.btn_compare.config(state=tk.DISABLED)
            self.dir_entry.config(state='disabled')
            self.tree.state(("disabled",))
        else:
            self.dir_entry.config(state='readonly')
            self.tree.state(("!disabled",))
            # 按钮状态交给 on_tree_select 处理

    def compare_with_external_html(self):
        selected_items = self.tree.selection()
        if len(selected_items) != 1:
            return
            
        internal_filepath = selected_items[0]
        internal_data = self.html_files[internal_filepath]

        external_filepath = filedialog.askopenfilename(
            title="选择要对比的外部 HTML 文件",
            filetypes=[("HTML Files", "*.html"), ("All Files", "*.*")]
        )
        if not external_filepath:
            return

        # 打开进度弹窗
        top = tk.Toplevel(self.root)
        top.title("文件深度对比中...")
        top.geometry("700x500")
        top.minsize(600, 400)
        
        # 构建进度UI
        frame_progress = tk.Frame(top, pady=50)
        frame_progress.pack(fill=tk.BOTH, expand=True)
        
        lbl_status = tk.Label(frame_progress, text="正在准备深度对比...", font=("Microsoft YaHei", 12))
        lbl_status.pack(pady=10)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(frame_progress, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, padx=50, pady=10)
        
        # 启动对比线程
        threading.Thread(target=self.compare_thread, 
                         args=(internal_data, external_filepath, top, frame_progress, lbl_status, progress_var), 
                         daemon=True).start()

    def _get_md5(self, filepath):
        m = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                # 按照 4MB 块读取，避免撑爆内存
                for chunk in iter(lambda: f.read(4096 * 1024), b''):
                    m.update(chunk)
            return m.hexdigest()
        except Exception:
            return None

    def _get_fast_md5(self, filepath, size, chunk_size=65536):
        """
        极速局部指纹：仅读取文件头部和尾部的 64KB 计算哈希。
        用于预先筛选，能避开99%以上的大文件全量 IO 读取耗时。
        """
        m = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                if size <= chunk_size * 2:
                    m.update(f.read())  # 文件很小，直接读完
                else:
                    m.update(f.read(chunk_size))  # 读头部
                    f.seek(-chunk_size, os.SEEK_END)
                    m.update(f.read(chunk_size))  # 读尾部
            return m.hexdigest()
        except Exception:
            return None

    def compare_thread(self, internal_data, external_filepath, top_window, frame_progress, lbl_status, progress_var):
        try:
            # 1. 解析外部 HTML
            self.root.after(0, lambda: lbl_status.config(text="正在解析外部HTML文件..."))
            img_re = re.compile(r'src=["\'](media/[^"\']+)["\']')
            video_re = re.compile(r'loadVideo\s*\(\s*this\s*,\s*["\'](media/[^"\']+)["\']\s*\)')
            audio_re = re.compile(r'<audio[^>]+src=["\'](media/[^"\']+)["\']')
            file_re = re.compile(r'href=["\'](files/[^"\']+)["\']')

            external_assets = set()
            with open(external_filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                external_assets.update(img_re.findall(content))
                external_assets.update(video_re.findall(content))
                external_assets.update(audio_re.findall(content))
                external_assets.update(file_re.findall(content))
                
            external_assets = {urllib.parse.unquote(a) for a in external_assets}
            
            # 2. 收集双方的基础信息 (读取大小)
            self.root.after(0, lambda: lbl_status.config(text="正在读取物理文件大小信息..."))
            internal_dir = self.base_dir
            external_dir = os.path.dirname(external_filepath)
            
            internal_info = {} # rel_path -> size
            for rel_path in internal_data['assets']:
                abs_p = os.path.join(internal_dir, os.path.normpath(rel_path))
                if os.path.exists(abs_p):
                    internal_info[rel_path] = os.path.getsize(abs_p)
                    
            external_info = {} # rel_path -> size
            for rel_path in external_assets:
                abs_p = os.path.join(external_dir, os.path.normpath(rel_path))
                if os.path.exists(abs_p):
                    external_info[rel_path] = os.path.getsize(abs_p)

            # 3. 性能优化核心：找出大小相同的交集并分组
            internal_by_size = {}
            for rp, size in internal_info.items(): 
                internal_by_size.setdefault(size, []).append(rp)
                
            external_by_size = {}
            for rp, size in external_info.items(): 
                external_by_size.setdefault(size, []).append(rp)

            common_sizes = set(internal_by_size.keys()) & set(external_by_size.keys())
            
            # 4. 计算签名 (双重特征预筛算法)
            internal_sigs = {} # signature (size, fast_md5, full_md5) -> list of rel_paths
            external_sigs = {}
            
            # Step A: 大小独一无二的文件直接归类，完全跳过哈希计算
            for size, paths in internal_by_size.items():
                if size not in common_sizes:
                    for rp in paths: internal_sigs.setdefault((size, None, None), []).append(rp)
                    
            for size, paths in external_by_size.items():
                if size not in common_sizes:
                    for rp in paths: external_sigs.setdefault((size, None, None), []).append(rp)
            
            total_hash_tasks = sum(len(internal_by_size[s]) + len(external_by_size[s]) for s in common_sizes)
            current_hash = 0

            # Step B: 针对大小相同的疑似重复文件，进行极速指纹过滤
            for size in common_sizes:
                int_paths = internal_by_size[size]
                ext_paths = external_by_size[size]

                ext_fast = {}
                for rp in ext_paths:
                    current_hash += 1
                    if current_hash % 10 == 0:
                        self.root.after(0, lambda p=(current_hash/(total_hash_tasks or 1)*100): progress_var.set(p))
                        self.root.after(0, lambda: lbl_status.config(text="预筛外部文件指纹... (极速)"))
                    ep = os.path.join(external_dir, os.path.normpath(rp))
                    ext_fast[rp] = self._get_fast_md5(ep, size)

                int_fast = {}
                for rp in int_paths:
                    current_hash += 1
                    if current_hash % 10 == 0:
                        self.root.after(0, lambda p=(current_hash/(total_hash_tasks or 1)*100): progress_var.set(p))
                        self.root.after(0, lambda: lbl_status.config(text="预筛当前文件指纹... (极速)"))
                    ip = os.path.join(internal_dir, os.path.normpath(rp))
                    int_fast[rp] = self._get_fast_md5(ip, size)

                # 找出碰撞的快速指纹
                shared_fast_hashes = set(ext_fast.values()) & set(int_fast.values()) - {None}

                # Step C: 只对局部特征命中的文件，进行全量 MD5 安全校验
                for rp, fh in int_fast.items():
                    if fh in shared_fast_hashes:
                        self.root.after(0, lambda: lbl_status.config(text="正在进行全量特征安全校验..."))
                        ip = os.path.join(internal_dir, os.path.normpath(rp))
                        full_md5 = self._get_md5(ip)
                        internal_sigs.setdefault((size, fh, full_md5), []).append(rp)
                    else:
                        internal_sigs.setdefault((size, fh, None), []).append(rp)

                for rp, fh in ext_fast.items():
                    if fh in shared_fast_hashes:
                        ep = os.path.join(external_dir, os.path.normpath(rp))
                        full_md5 = self._get_md5(ep)
                        external_sigs.setdefault((size, fh, full_md5), []).append(rp)
                    else:
                        external_sigs.setdefault((size, fh, None), []).append(rp)

            # 5. 集合运算（基于严谨组合指纹的比对）
            set_internal_sigs = set(internal_sigs.keys())
            set_external_sigs = set(external_sigs.keys())

            sig_added = set_external_sigs - set_internal_sigs
            sig_missing = set_internal_sigs - set_external_sigs
            sig_common = set_internal_sigs & set_external_sigs

            # 6. 转回显示名称（如果多个不同路径的文件哈希一样，把它们拼在一起展示给你）
            added_list = [f"{', '.join(external_sigs[sig])} (大小: {self.format_size(sig[0])})" for sig in sig_added]
            missing_list = [f"{', '.join(internal_sigs[sig])} (大小: {self.format_size(sig[0])})" for sig in missing_list] # bug fix
            missing_list = [f"{', '.join(internal_sigs[sig])} (大小: {self.format_size(sig[0])})" for sig in sig_missing]
            common_list = [f"[内] {', '.join(internal_sigs[sig])}  ==与==  [外] {', '.join(external_sigs[sig])}" for sig in sig_common]

            # 显示结果UI
            self.root.after(0, lambda: self._show_comparison_ui(
                top_window, frame_progress, 
                internal_data['filename'], os.path.basename(external_filepath),
                added_list, missing_list, common_list
            ))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"深度对比发生错误: {str(e)}", parent=top_window))
            self.root.after(0, top_window.destroy)

    def _show_comparison_ui(self, top_window, frame_progress, internal_name, external_name, added, missing, common):
        # 隐藏进度条框架
        frame_progress.pack_forget()
        top_window.title("深度分析对比结果")
        
        # 顶部信息区域
        info_frame = tk.Frame(top_window, padx=10, pady=10)
        info_frame.pack(fill=tk.X)
        
        tk.Label(info_frame, text=f"当前选择: {internal_name}", font=("Microsoft YaHei", 10, "bold"), fg="#1976D2").pack(anchor='w')
        tk.Label(info_frame, text=f"外部对比: {external_name}", font=("Microsoft YaHei", 10, "bold"), fg="#388E3C").pack(anchor='w', pady=(5,0))
        tk.Label(info_frame, text=f"共有(内容一致): {len(common)} 种 | 外部新增(多出): {len(added)} 种 | 外部缺少: {len(missing)} 种", pady=5, fg="#D32F2F").pack(anchor='w')
        
        # 使用 Notebook 创建选项卡展示详细列表
        notebook = ttk.Notebook(top_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        frame_added = ttk.Frame(notebook)
        notebook.add(frame_added, text=f"外部多出的内容 ({len(added)})")
        self._create_asset_list(frame_added, added)
        
        frame_missing = ttk.Frame(notebook)
        notebook.add(frame_missing, text=f"外部缺少的内容 ({len(missing)})")
        self._create_asset_list(frame_missing, missing)
        
        frame_common = ttk.Frame(notebook)
        notebook.add(frame_common, text=f"两边都有的内容 ({len(common)})")
        self._create_asset_list(frame_common, common)

    def _create_asset_list(self, parent_frame, assets):
        scrollbar = ttk.Scrollbar(parent_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 加宽列表方便看长名字和对照结果
        listbox = tk.Listbox(parent_frame, yscrollcommand=scrollbar.set, font=("Consolas", 10))
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
        scrollbar.config(command=listbox.yview)
        
        if not assets:
            listbox.insert(tk.END, "（空）")
            listbox.config(fg="gray")
        else:
            for asset in sorted(list(assets)):
                listbox.insert(tk.END, asset)

    # ==========================
    # 新增：与外部完整存档合并去重功能
    # ==========================
    def start_dedup_process(self):
        if not self.base_dir:
            messagebox.showwarning("提示", "请先选择并扫描当前备份目录！")
            return
            
        ext_dir = filedialog.askdirectory(title="选择作为参照的【外部聊天记录完整备份目录】")
        if not ext_dir:
            return
            
        if os.path.abspath(ext_dir) == os.path.abspath(self.base_dir):
            messagebox.showwarning("提示", "外部存档目录不能与当前目录相同！")
            return

        # 启动去重进度弹窗
        top = tk.Toplevel(self.root)
        top.title("外部存档合并去重分析")
        top.geometry("750x550")
        top.minsize(650, 450)
        top.transient(self.root)
        top.grab_set() # 设置为模态窗口
        
        frame_progress = tk.Frame(top, pady=20, padx=20)
        frame_progress.pack(fill=tk.BOTH, expand=True)
        
        lbl_title = tk.Label(frame_progress, text="正在分析两个存档的相似度...", font=("Microsoft YaHei", 12, "bold"))
        lbl_title.pack(pady=10)
        
        lbl_status = tk.Label(frame_progress, text="准备扫描...", font=("Microsoft YaHei", 10))
        lbl_status.pack(pady=5)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(frame_progress, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, pady=10)
        
        # 滚动日志框
        text_log = tk.Text(frame_progress, height=12, font=("Consolas", 9), bg="#f5f5f5")
        text_log.pack(fill=tk.BOTH, expand=True, pady=10)
        
        btn_execute = tk.Button(frame_progress, text="开始执行合并并释放空间", font=("Microsoft YaHei", 11, "bold"), bg="#F44336", fg="white", state=tk.DISABLED)
        btn_execute.pack(pady=10)
        
        threading.Thread(target=self.dedup_scan_thread, 
                         args=(ext_dir, top, lbl_status, progress_var, text_log, btn_execute), 
                         daemon=True).start()

    def log_to_text(self, text_widget, msg):
        self.root.after(0, lambda: text_widget.insert(tk.END, msg + "\n"))
        self.root.after(0, lambda: text_widget.see(tk.END))

    def dedup_scan_thread(self, ext_dir, top_window, lbl_status, progress_var, text_log, btn_execute):
        try:
            self.root.after(0, lambda: lbl_status.config(text="正在收集当前存档的有效资源信息..."))
            current_assets = set()
            for data in self.html_files.values():
                current_assets.update(data['assets'])
                
            caa_info = {} # rel_path -> size
            for rel_path in current_assets:
                abs_p = os.path.join(self.base_dir, os.path.normpath(rel_path))
                if os.path.exists(abs_p):
                    caa_info[rel_path] = os.path.getsize(abs_p)
            
            self.root.after(0, lambda: lbl_status.config(text="正在极速扫描外部存档资源信息..."))
            eaa_info = {} # abs_path -> size
            for folder in ["media", "files"]:
                d = os.path.join(ext_dir, folder)
                if os.path.exists(d):
                    for entry in os.scandir(d):
                        if entry.is_file():
                            eaa_info[entry.path] = entry.stat().st_size
                            
            self.log_to_text(text_log, f"当前存档关联媒体/文件数: {len(caa_info)}")
            self.log_to_text(text_log, f"外部参照存档媒体/文件数: {len(eaa_info)}")
            
            # 第一阶段：尺寸聚类
            self.root.after(0, lambda: lbl_status.config(text="正在进行大小匹配预处理算法..."))
            caa_by_size = {}
            for rp, size in caa_info.items(): 
                caa_by_size.setdefault(size, []).append(rp)
                
            eaa_by_size = {}
            for rp, size in eaa_info.items(): 
                eaa_by_size.setdefault(size, []).append(rp)
                
            common_sizes = set(caa_by_size.keys()) & set(eaa_by_size.keys())
            self.log_to_text(text_log, f"共锁定可能相同的文件尺寸: {len(common_sizes)} 种")
            
            # 第二阶段：双重哈希指纹校验 (局部指纹预筛 -> 全量指纹确认)
            mapping = {} # current_rel_path -> ext_abs_path
            total_tasks = sum(len(caa_by_size[s]) + len(eaa_by_size[s]) for s in common_sizes)
            current_task = 0
            
            for size in common_sizes:
                int_paths = caa_by_size[size]
                ext_paths = eaa_by_size[size]
                
                # 1. 提取外部文件的局部特征 (Fast Hash)
                ext_fast_map = {} # fast_hash -> list of abs_paths
                for ep in ext_paths:
                    current_task += 1
                    if current_task % 20 == 0:
                        self.root.after(0, lambda p=(current_task/(total_tasks or 1)*100): progress_var.set(p))
                        self.root.after(0, lambda: lbl_status.config(text="正在进行极速指纹预筛 (外部文件)..."))
                    
                    fh = self._get_fast_md5(ep, size)
                    if fh:
                        ext_fast_map.setdefault(fh, []).append(ep)
                        
                # 2. 提取当前文件的局部特征，按需全量验证
                ext_full_cache = {} # 延迟计算：按需缓存外部文件的全量MD5
                
                for ip in int_paths:
                    current_task += 1
                    if current_task % 20 == 0:
                        self.root.after(0, lambda p=(current_task/(total_tasks or 1)*100): progress_var.set(p))
                        self.root.after(0, lambda: lbl_status.config(text="正在进行极速指纹预筛 (当前文件)..."))
                        
                    abs_ip = os.path.join(self.base_dir, os.path.normpath(ip))
                    fh = self._get_fast_md5(abs_ip, size)
                    
                    if fh and fh in ext_fast_map:
                        # 局部特征一致！执行全量MD5终极校验确保万无一失
                        self.root.after(0, lambda: lbl_status.config(text="发现局部特征一致的媒体，执行全量安全对比..."))
                        full_ip_md5 = self._get_md5(abs_ip)
                        if not full_ip_md5:
                            continue
                            
                        matched = False
                        for ep in ext_fast_map[fh]:
                            # 获取外部文件的全量MD5 (带缓存，同一个文件只算一次)
                            if ep not in ext_full_cache:
                                ext_full_cache[ep] = self._get_md5(ep)
                            
                            if full_ip_md5 == ext_full_cache[ep]:
                                mapping[ip] = ep
                                matched = True
                                break # 找到一个匹配的外部文件即可
                        
                        if matched:
                            continue
                        
            total_freed_bytes = sum(caa_info[rp] for rp in mapping.keys())
            
            self.root.after(0, lambda: lbl_status.config(text="分析完成，请确认操作。"))
            self.log_to_text(text_log, "\n" + "-"*45)
            self.log_to_text(text_log, f"【分析结果报告】")
            self.log_to_text(text_log, f"发现完全相同的冗余媒体/文件: {len(mapping)} 个")
            self.log_to_text(text_log, f"预计可释放当前存储空间: {self.format_size(total_freed_bytes)}")
            self.log_to_text(text_log, f"\n【即将执行的合并逻辑】")
            self.log_to_text(text_log, f"1. 自动重写受影响的 HTML 链接，指引其加载外部存档中的资源。")
            self.log_to_text(text_log, f"2. 修改前的 HTML 文件将安全移至本目录下的 merge_back 备份夹中。")
            self.log_to_text(text_log, f"3. 剥离并永久删除这 {len(mapping)} 个当前目录中的冗余文件以释放空间。")
            
            if len(mapping) > 0:
                self.root.after(0, lambda: btn_execute.config(state=tk.NORMAL, 
                    command=lambda: self.start_execute_dedup(mapping, ext_dir, top_window, lbl_status, progress_var, btn_execute)))
            else:
                self.log_to_text(text_log, "\n未发现可去重的重复文件，操作结束。")
                self.root.after(0, lambda: btn_execute.config(text="退出", bg="#4CAF50", state=tk.NORMAL, command=top_window.destroy))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"分析过程出错: {str(e)}", parent=top_window))

    def start_execute_dedup(self, mapping, ext_dir, top_window, lbl_status, progress_var, btn_execute):
        confirm = messagebox.askyesno("最后确认", "该操作将修改HTML链接并删除当前备份中的重复媒体文件！\n\n注意：合并后，外部存档作为参照物不能再被移动或删除，否则会导致加载失败。\n\n您确认开始合并吗？", parent=top_window)
        if not confirm:
            return
            
        btn_execute.config(state=tk.DISABLED)
        threading.Thread(target=self.execute_dedup_thread, 
                         args=(mapping, top_window, lbl_status, progress_var), 
                         daemon=True).start()

    def execute_dedup_thread(self, mapping, top_window, lbl_status, progress_var):
        try:
            merge_back_dir = os.path.join(self.base_dir, "merge_back")
            os.makedirs(merge_back_dir, exist_ok=True)
            
            # 使用带前缀匹配的正则，保证精确重写链接内容
            patterns = [
                r'(src=["\'])(media/[^"\']+)["\']',
                r'(loadVideo\s*\(\s*this\s*,\s*["\'])(media/[^"\']+)["\']',
                r'(href=["\'])(files/[^"\']+)["\']'
            ]
            
            # 闭包函数：为了在正则替换时根据 mapping 表动态计算新路径
            def get_replacer():
                def repl(match):
                    prefix = match.group(1)       # 如: src="
                    orig_path = match.group(2)    # 如: media/123.jpg
                    suffix = match.group(0)[len(prefix)+len(orig_path):] # 尾部引号等
                    
                    decoded = urllib.parse.unquote(orig_path)
                    # 如果该资源已被去重，则将它修正为指向外部存档的相对路径
                    if decoded in mapping:
                        ext_abs = mapping[decoded]
                        # 核心计算：从当前目录到外部存档文件的相对路径，并保持正斜杠
                        rel_p = os.path.relpath(ext_abs, self.base_dir).replace('\\', '/')
                        # 安全的 URL 编码（保留路径分隔符）
                        new_path = urllib.parse.quote(rel_p, safe='/')
                        return f"{prefix}{new_path}{suffix}"
                    return match.group(0)
                return repl

            replacer = get_replacer()
            
            total_htmls = len(self.html_files)
            modified_count = 0
            
            # 1. 遍历并修改具有交叉引用的 HTML 文件
            for i, (filepath, data) in enumerate(self.html_files.items()):
                self.root.after(0, lambda p=(i/total_htmls*50): progress_var.set(p))
                self.root.after(0, lambda fn=data['filename']: lbl_status.config(text=f"正在分析 HTML 链接: {fn}"))
                
                # 如果该 HTML 完全没有引用我们需要去重的文件，直接跳过，不修改不备份
                if not (data['assets'] & set(mapping.keys())):
                    continue
                    
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                # 应用所有正则替换
                for p in patterns:
                    content = re.sub(p, replacer, content)
                    
                # 安全备份：将原文件放入 merge_back 目录 (原样移出)
                filename = os.path.basename(filepath)
                backup_path = os.path.join(merge_back_dir, filename)
                shutil.move(filepath, backup_path)
                
                # 写回修改后的 HTML 到原位
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                modified_count += 1
                
            # 2. 一次性删除冗余的资源文件以释放空间
            total_assets = len(mapping)
            deleted_count = 0
            freed_space = 0
            for i, rel_path in enumerate(mapping.keys()):
                self.root.after(0, lambda p=(50 + i/total_assets*50): progress_var.set(p))
                self.root.after(0, lambda: lbl_status.config(text=f"正在物理删除冗余文件 ({i}/{total_assets})..."))
                
                abs_p = os.path.join(self.base_dir, os.path.normpath(rel_path))
                if os.path.exists(abs_p):
                    freed_space += os.path.getsize(abs_p)
                    os.chmod(abs_p, stat.S_IWRITE)  # 强制移除只读属性
                    os.remove(abs_p)
                    deleted_count += 1
                    
            self.root.after(0, lambda: messagebox.showinfo("合并去重完成", 
                f"跨目录合并处理完毕！\n\n已成功更新引用链接的 HTML: {modified_count} 个\n"
                f"(原文件已安全备份在 merge_back/ 目录中)\n\n"
                f"已删除重复文件: {deleted_count} 个\n"
                f"为您释放空间: {self.format_size(freed_space)}", parent=top_window))
                
            self.root.after(0, top_window.destroy)
            self.root.after(0, self.scan_directory_thread) # 重新扫描更新主界面的数据统计

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"执行合并过程中发生严重错误: {str(e)}", parent=top_window))

    # ==========================
    # 新增：当前目录内部去重合并功能
    # ==========================
    def start_internal_dedup_process(self):
        if not self.base_dir:
            messagebox.showwarning("提示", "请先选择并扫描当前备份目录！")
            return

        # 启动去重进度弹窗
        top = tk.Toplevel(self.root)
        top.title("当前存档内部去重分析")
        top.geometry("750x550")
        top.minsize(650, 450)
        top.transient(self.root)
        top.grab_set() 
        
        frame_progress = tk.Frame(top, pady=20, padx=20)
        frame_progress.pack(fill=tk.BOTH, expand=True)
        
        lbl_title = tk.Label(frame_progress, text="正在分析当前存档的内部冗余...", font=("Microsoft YaHei", 12, "bold"))
        lbl_title.pack(pady=10)
        
        lbl_status = tk.Label(frame_progress, text="准备扫描...", font=("Microsoft YaHei", 10))
        lbl_status.pack(pady=5)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(frame_progress, variable=progress_var, maximum=100)
        progress_bar.pack(fill=tk.X, pady=10)
        
        text_log = tk.Text(frame_progress, height=12, font=("Consolas", 9), bg="#fdfdfd")
        text_log.pack(fill=tk.BOTH, expand=True, pady=10)
        
        btn_execute = tk.Button(frame_progress, text="开始执行内部合并并释放空间", font=("Microsoft YaHei", 11, "bold"), bg="#F44336", fg="white", state=tk.DISABLED)
        btn_execute.pack(pady=10)
        
        threading.Thread(target=self.internal_dedup_scan_thread, 
                         args=(top, lbl_status, progress_var, text_log, btn_execute), 
                         daemon=True).start()

    def internal_dedup_scan_thread(self, top_window, lbl_status, progress_var, text_log, btn_execute):
        try:
            self.root.after(0, lambda: lbl_status.config(text="正在收集当前存档的有效资源信息..."))
            current_assets = set()
            for data in self.html_files.values():
                current_assets.update(data['assets'])
                
            caa_info = {} # rel_path -> size
            for rel_path in current_assets:
                abs_p = os.path.join(self.base_dir, os.path.normpath(rel_path))
                if os.path.exists(abs_p):
                    caa_info[rel_path] = os.path.getsize(abs_p)
            
            # 第一阶段：尺寸聚类
            caa_by_size = {}
            for rp, size in caa_info.items(): 
                caa_by_size.setdefault(size, []).append(rp)
                
            # 过滤出大小出现过至少2次的文件群组（独一无二的大小的文件绝不可能有重复）
            duplicate_sizes = {size: paths for size, paths in caa_by_size.items() if len(paths) > 1}
            
            self.log_to_text(text_log, f"当前存档总媒体/文件数: {len(caa_info)}")
            self.log_to_text(text_log, f"锁定存在潜在内部重复的尺寸: {len(duplicate_sizes)} 种")
            
            mapping = {} # redundant_rel_path -> master_rel_path
            
            total_tasks = sum(len(paths) for paths in duplicate_sizes.values())
            current_task = 0
            
            for size, paths in duplicate_sizes.items():
                fast_map = {}
                for ip in paths:
                    current_task += 1
                    if current_task % 10 == 0:
                        self.root.after(0, lambda p=(current_task/(total_tasks*2 or 1)*100): progress_var.set(p))
                        self.root.after(0, lambda: lbl_status.config(text="正在进行极速局部指纹预筛..."))
                        
                    abs_ip = os.path.join(self.base_dir, os.path.normpath(ip))
                    fh = self._get_fast_md5(abs_ip, size)
                    if fh:
                        fast_map.setdefault(fh, []).append(ip)
                        
                # 进一步进行全量验证 (只针对极速特征重合的文件)
                for fh, f_paths in fast_map.items():
                    if len(f_paths) > 1:
                        full_map = {}
                        for ip in f_paths:
                            current_task += 1
                            self.root.after(0, lambda p=(50 + current_task/(total_tasks*2 or 1)*50): progress_var.set(p))
                            self.root.after(0, lambda: lbl_status.config(text="发现局部特征一致的媒体，执行全量安全对比..."))
                            
                            abs_ip = os.path.join(self.base_dir, os.path.normpath(ip))
                            full_md5 = self._get_md5(abs_ip)
                            if full_md5:
                                full_map.setdefault(full_md5, []).append(ip)
                                
                        # 真正内容完全一致的重复项
                        for fm, fm_paths in full_map.items():
                            if len(fm_paths) > 1:
                                # 排序，确保不管重头跑多少次，选出的唯一保留项(master)都是固定的（字母序列第一的保留）
                                fm_paths.sort()
                                master = fm_paths[0]
                                for redundant in fm_paths[1:]:
                                    mapping[redundant] = master
            
            total_freed_bytes = sum(caa_info[rp] for rp in mapping.keys())
            
            self.root.after(0, lambda: lbl_status.config(text="内部冗余分析完成，请确认操作。"))
            self.log_to_text(text_log, "\n" + "-"*45)
            self.log_to_text(text_log, f"【内部去重分析报告】")
            self.log_to_text(text_log, f"发现完全一致的内部冗余媒体/文件: {len(mapping)} 个")
            self.log_to_text(text_log, f"预计可释放本地存储空间: {self.format_size(total_freed_bytes)}")
            self.log_to_text(text_log, f"\n【即将执行的合并逻辑】")
            self.log_to_text(text_log, f"1. 自动重写 HTML 链接，将重复的引用指向保留下来的唯一主文件。")
            self.log_to_text(text_log, f"2. 修改前的 HTML 文件将安全移至 merge_back/ 备份夹中。")
            self.log_to_text(text_log, f"3. 剥离并永久删除这 {len(mapping)} 个冗余文件。")
            
            if len(mapping) > 0:
                self.root.after(0, lambda: btn_execute.config(state=tk.NORMAL, 
                    command=lambda: self.start_execute_internal_dedup(mapping, top_window, lbl_status, progress_var, btn_execute)))
            else:
                self.log_to_text(text_log, "\n未发现可去重的内部重复文件，恭喜，您的存档非常纯粹！")
                self.root.after(0, lambda: btn_execute.config(text="退出", bg="#4CAF50", state=tk.NORMAL, command=top_window.destroy))
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"内部去重分析过程出错: {str(e)}", parent=top_window))

    def start_execute_internal_dedup(self, mapping, top_window, lbl_status, progress_var, btn_execute):
        confirm = messagebox.askyesno("最后确认", "该操作将修改HTML链接并删除目录内部的冗余媒体文件！\n\n您确认开始合并去重吗？", parent=top_window)
        if not confirm:
            return
            
        btn_execute.config(state=tk.DISABLED)
        threading.Thread(target=self.execute_internal_dedup_thread, 
                         args=(mapping, top_window, lbl_status, progress_var), 
                         daemon=True).start()

    def execute_internal_dedup_thread(self, mapping, top_window, lbl_status, progress_var):
        try:
            merge_back_dir = os.path.join(self.base_dir, "merge_back")
            os.makedirs(merge_back_dir, exist_ok=True)
            
            patterns = [
                r'(src=["\'])(media/[^"\']+)["\']',
                r'(loadVideo\s*\(\s*this\s*,\s*["\'])(media/[^"\']+)["\']',
                r'(href=["\'])(files/[^"\']+)["\']'
            ]
            
            def get_replacer():
                def repl(match):
                    prefix = match.group(1)
                    orig_path = match.group(2)
                    suffix = match.group(0)[len(prefix)+len(orig_path):]
                    
                    decoded = urllib.parse.unquote(orig_path)
                    if decoded in mapping:
                        master_rel = mapping[decoded]
                        # 对于内部去重，两者都是相对于 HTML 根目录的路径，所以不需要 ../ 跳转，直接替换即可
                        new_path = urllib.parse.quote(master_rel, safe='/')
                        return f"{prefix}{new_path}{suffix}"
                    return match.group(0)
                return repl

            replacer = get_replacer()
            
            total_htmls = len(self.html_files)
            modified_count = 0
            
            # 1. 遍历并修改具有引用的 HTML 文件
            for i, (filepath, data) in enumerate(self.html_files.items()):
                self.root.after(0, lambda p=(i/total_htmls*50): progress_var.set(p))
                self.root.after(0, lambda fn=data['filename']: lbl_status.config(text=f"正在分析 HTML 链接: {fn}"))
                
                # 如果该 HTML 完全没有引用我们要去重的文件，跳过
                if not (data['assets'] & set(mapping.keys())):
                    continue
                    
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    
                for p in patterns:
                    content = re.sub(p, replacer, content)
                    
                filename = os.path.basename(filepath)
                backup_path = os.path.join(merge_back_dir, filename)
                shutil.move(filepath, backup_path)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                modified_count += 1
                
            # 2. 一次性删除内部冗余的物理文件
            total_assets = len(mapping)
            deleted_count = 0
            freed_space = 0
            for i, rel_path in enumerate(mapping.keys()):
                self.root.after(0, lambda p=(50 + i/total_assets*50): progress_var.set(p))
                self.root.after(0, lambda: lbl_status.config(text=f"正在永久删除冗余文件 ({i}/{total_assets})..."))
                
                abs_p = os.path.join(self.base_dir, os.path.normpath(rel_path))
                if os.path.exists(abs_p):
                    freed_space += os.path.getsize(abs_p)
                    os.chmod(abs_p, stat.S_IWRITE)  # 强制移除只读属性
                    os.remove(abs_p)
                    deleted_count += 1
                    
            self.root.after(0, lambda: messagebox.showinfo("内部去重完成", 
                f"当前存档内部去重处理完毕！\n\n已成功优化引用链接的 HTML: {modified_count} 个\n"
                f"(修改前的老版本 HTML 已安全退至 merge_back/ 目录中)\n\n"
                f"已彻底删除内部重复文件: {deleted_count} 个\n"
                f"为您释放了本地空间: {self.format_size(freed_space)}", parent=top_window))
                
            self.root.after(0, top_window.destroy)
            self.root.after(0, self.scan_directory_thread) # 重新扫描刷新 UI

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"内部去重执行过程中发生严重错误: {str(e)}", parent=top_window))

if __name__ == "__main__":
    root = tk.Tk()
    app = ChatBackupCleaner(root)
    root.mainloop()