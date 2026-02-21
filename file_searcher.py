import json
import os
import re
import queue
import threading
import datetime
from pathlib import Path
from tkinter import (
    Tk, StringVar, BooleanVar, Frame, Label, Entry, Button,
    Checkbutton, filedialog, messagebox, END, Menu
)
from tkinter import ttk

try:
    import windnd
    HAS_WINDND = True
except ImportError:
    HAS_WINDND = False

LIGHT_THEME = {
    "name": "light",
    "BG": "#F7F5F2",
    "CARD_BG": "#FFFFFF",
    "BORDER": "#E2DDD5",
    "TEXT": "#3D3528",
    "TEXT_LIGHT": "#8C8476",
    "PLACEHOLDER": "#B8AFA3",
    "PRIMARY": "#5B8A72",
    "PRIMARY_HOVER": "#4A755F",
    "PRIMARY_TEXT": "#FFFFFF",
    "CANCEL": "#C97B63",
    "CANCEL_HOVER": "#B56A53",
    "CANCEL_TEXT": "#FFFFFF",
    "ROW_ODD": "#FFFFFF",
    "ROW_EVEN": "#F9F7F4",
    "SELECT_BG": "#D4E8DB",
    "HEADER_BG": "#EDE9E3",
    "SUCCESS": "#5B8A72",
    "WARNING": "#D4A843",
    "INFO": "#6B8EAE",
    "TOGGLE_BG": "#EDE9E3",
}

DARK_THEME = {
    "name": "dark",
    "BG": "#1E1E2E",
    "CARD_BG": "#2A2A3C",
    "BORDER": "#3E3E52",
    "TEXT": "#E0DDD5",
    "TEXT_LIGHT": "#9A96A6",
    "PLACEHOLDER": "#6C6880",
    "PRIMARY": "#6DBFA0",
    "PRIMARY_HOVER": "#5AA98B",
    "PRIMARY_TEXT": "#1E1E2E",
    "CANCEL": "#E08870",
    "CANCEL_HOVER": "#CC7660",
    "CANCEL_TEXT": "#1E1E2E",
    "ROW_ODD": "#2A2A3C",
    "ROW_EVEN": "#323244",
    "SELECT_BG": "#3D5A4E",
    "HEADER_BG": "#333346",
    "SUCCESS": "#6DBFA0",
    "WARNING": "#E0C068",
    "INFO": "#7EAED0",
    "TOGGLE_BG": "#333346",
}

HISTORY_FILE = os.path.join(os.path.dirname(__file__), ".search_history.json")
MAX_HISTORY = 20

class FileSearchApp:
    POLL_INTERVAL_MS = 50
    FONT_FAMILY = "Meiryo UI"

    def __init__(self, root: Tk):
        self.root = root
        self.root.title("📂 ファイル検索ツール")
        self.root.geometry("1020x720")
        self.root.minsize(780, 560)

        self._theme = LIGHT_THEME
        self.C = self._theme

        self.folder_var = StringVar()
        self.keyword_var = StringVar()
        self.ext_var = StringVar()
        self.regex_var = BooleanVar(value=False)
        self.subfolder_var = BooleanVar(value=True)
        self.date_filter_var = StringVar(value="すべて")

        self._cancel_event = threading.Event()
        self._result_queue: queue.Queue = queue.Queue()
        self._search_thread: threading.Thread | None = None
        self._sort_reverse: dict[str, bool] = {}
        self._row_count = 0

        self._history: list[str] = self._load_history()

        self._apply_styles()
        self._build_ui()
        self._build_context_menu()
        self._setup_drag_and_drop()

    def _apply_styles(self):
        C = self.C
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("App.TFrame", background=C["BG"])
        style.configure("Card.TFrame", background=C["CARD_BG"])

        for name, bg in [("App", C["BG"]), ("Card", C["CARD_BG"])]:
            style.configure(
                f"{name}.TLabel", background=bg, foreground=C["TEXT"],
                font=(self.FONT_FAMILY, 10),
            )

        style.configure(
            "Heading.TLabel", background=C["BG"], foreground=C["TEXT"],
            font=(self.FONT_FAMILY, 14, "bold"),
        )
        style.configure(
            "Sub.TLabel", background=C["CARD_BG"], foreground=C["TEXT_LIGHT"],
            font=(self.FONT_FAMILY, 9),
        )
        style.configure(
            "StatusOK.TLabel", background=C["BG"], foreground=C["SUCCESS"],
            font=(self.FONT_FAMILY, 10, "bold"),
        )
        style.configure(
            "StatusSearch.TLabel", background=C["BG"], foreground=C["INFO"],
            font=(self.FONT_FAMILY, 10, "bold"),
        )
        style.configure(
            "Count.TLabel", background=C["BG"], foreground=C["TEXT_LIGHT"],
            font=(self.FONT_FAMILY, 9),
        )

        style.configure(
            "Search.TButton", background=C["PRIMARY"],
            foreground=C["PRIMARY_TEXT"],
            font=(self.FONT_FAMILY, 10, "bold"), padding=(16, 8), borderwidth=0,
        )
        style.map("Search.TButton",
                  background=[("active", C["PRIMARY_HOVER"]),
                               ("disabled", C["BORDER"])],
                  foreground=[("disabled", C["TEXT_LIGHT"])])

        style.configure(
            "Cancel.TButton", background=C["CANCEL"],
            foreground=C["CANCEL_TEXT"],
            font=(self.FONT_FAMILY, 10), padding=(16, 8), borderwidth=0,
        )
        style.map("Cancel.TButton",
                  background=[("active", C["CANCEL_HOVER"]),
                               ("disabled", C["BORDER"])],
                  foreground=[("disabled", C["TEXT_LIGHT"])])

        style.configure(
            "Browse.TButton", background=C["HEADER_BG"],
            foreground=C["TEXT"],
            font=(self.FONT_FAMILY, 9), padding=(10, 6), borderwidth=0,
        )
        style.map("Browse.TButton",
                  background=[("active", C["BORDER"])])

        style.configure(
            "Toggle.TButton", background=C["TOGGLE_BG"],
            foreground=C["TEXT"],
            font=(self.FONT_FAMILY, 9), padding=(10, 6), borderwidth=0,
        )
        style.map("Toggle.TButton",
                  background=[("active", C["BORDER"])])

        style.configure(
            "App.TEntry", fieldbackground=C["CARD_BG"],
            foreground=C["TEXT"], bordercolor=C["BORDER"],
            lightcolor=C["BORDER"], darkcolor=C["BORDER"],
            borderwidth=1, padding=(8, 6),
        )
        style.map("App.TEntry",
                  bordercolor=[("focus", C["PRIMARY"])],
                  lightcolor=[("focus", C["PRIMARY"])])

        style.configure(
            "App.TCombobox", fieldbackground=C["CARD_BG"],
            foreground=C["TEXT"], bordercolor=C["BORDER"],
            lightcolor=C["BORDER"], darkcolor=C["BORDER"],
            arrowcolor=C["TEXT"], padding=(8, 6),
        )
        style.map("App.TCombobox",
                  bordercolor=[("focus", C["PRIMARY"])],
                  lightcolor=[("focus", C["PRIMARY"])],
                  fieldbackground=[("readonly", C["CARD_BG"])])

        style.configure(
            "App.TCheckbutton", background=C["CARD_BG"],
            foreground=C["TEXT"], font=(self.FONT_FAMILY, 10),
        )
        style.map("App.TCheckbutton",
                  background=[("active", C["CARD_BG"])])

        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=C["BORDER"], background=C["PRIMARY"],
            borderwidth=0, thickness=6,
        )

        style.configure(
            "Card.TLabelframe", background=C["CARD_BG"],
            foreground=C["TEXT"], bordercolor=C["BORDER"],
            relief="flat", borderwidth=1,
        )
        style.configure(
            "Card.TLabelframe.Label", background=C["CARD_BG"],
            foreground=C["TEXT"], font=(self.FONT_FAMILY, 10, "bold"),
        )

        style.configure(
            "App.Treeview", background=C["CARD_BG"],
            foreground=C["TEXT"], fieldbackground=C["CARD_BG"],
            borderwidth=0, font=(self.FONT_FAMILY, 9), rowheight=28,
        )
        style.configure(
            "App.Treeview.Heading", background=C["HEADER_BG"],
            foreground=C["TEXT"], font=(self.FONT_FAMILY, 9, "bold"),
            borderwidth=0, relief="flat", padding=(8, 6),
        )
        style.map("App.Treeview.Heading",
                  background=[("active", C["BORDER"])])
        style.map("App.Treeview",
                  background=[("selected", C["SELECT_BG"])],
                  foreground=[("selected", C["TEXT"])])

    def _refresh_theme(self):
        self._apply_styles()
        C = self.C

        self.root.configure(bg=C["BG"])
        self._set_widget_bg(self.root, C)

        self.tree.tag_configure("odd", background=C["ROW_ODD"])
        self.tree.tag_configure("even", background=C["ROW_EVEN"])
        self._reapply_row_tags()

        if C["name"] == "dark":
            self.btn_theme.config(text="☀️ ライト")
        else:
            self.btn_theme.config(text="🌙 ダーク")

    @staticmethod
    def _set_widget_bg(widget, C):
        try:
            wtype = widget.winfo_class()
            if wtype in ("Frame", "TFrame", "Labelframe", "TLabelframe"):
                widget.configure(background=C["CARD_BG"])
            elif wtype in ("Tk", "Toplevel"):
                widget.configure(background=C["BG"])
        except Exception:
            pass
        for child in widget.winfo_children():
            FileSearchApp._set_widget_bg(child, C)

    def _toggle_theme(self):
        if self._theme["name"] == "light":
            self._theme = DARK_THEME
        else:
            self._theme = LIGHT_THEME
        self.C = self._theme
        self._refresh_theme()

    def _build_ui(self):
        C = self.C
        px = 16

        header = ttk.Frame(self.root, style="App.TFrame")
        header.pack(fill="x", padx=px, pady=(14, 4))
        ttk.Label(
            header, text="📂 ファイル検索ツール", style="Heading.TLabel"
        ).pack(side="left")
        ttk.Label(
            header, text="PC内のファイルをすばやく探そう！",
            style="App.TLabel", foreground=C["TEXT_LIGHT"],
        ).pack(side="left", padx=(12, 0))

        self.btn_theme = ttk.Button(
            header, text="🌙 ダーク", style="Toggle.TButton",
            command=self._toggle_theme,
        )
        self.btn_theme.pack(side="right")

        cond = ttk.LabelFrame(
            self.root, text=" 🔍 検索条件 ",
            style="Card.TLabelframe", padding=14,
        )
        cond.pack(fill="x", padx=px, pady=6)

        r1 = ttk.Frame(cond, style="Card.TFrame")
        r1.pack(fill="x", pady=(0, 6))
        ttk.Label(r1, text="📁 フォルダ", style="Card.TLabel", width=14).pack(
            side="left"
        )
        self.entry_folder = ttk.Entry(
            r1, textvariable=self.folder_var, style="App.TEntry"
        )
        self.entry_folder.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(
            r1, text="参照…", style="Browse.TButton",
            command=self._browse_folder,
        ).pack(side="left")

        r2 = ttk.Frame(cond, style="Card.TFrame")
        r2.pack(fill="x", pady=(0, 6))
        ttk.Label(r2, text="🔎 ファイル名", style="Card.TLabel", width=14).pack(
            side="left"
        )
        self.combo_keyword = ttk.Combobox(
            r2, textvariable=self.keyword_var, style="App.TCombobox",
            values=self._history,
        )
        self.combo_keyword.pack(side="left", fill="x", expand=True)

        r3 = ttk.Frame(cond, style="Card.TFrame")
        r3.pack(fill="x", pady=(0, 6))
        ttk.Label(r3, text="📄 拡張子", style="Card.TLabel", width=14).pack(
            side="left"
        )
        self.entry_ext = ttk.Entry(
            r3, textvariable=self.ext_var, style="App.TEntry"
        )
        self.entry_ext.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Label(r3, text="例: .py, .txt", style="Sub.TLabel").pack(
            side="left"
        )

        r4 = ttk.Frame(cond, style="Card.TFrame")
        r4.pack(fill="x", pady=(0, 2))

        ttk.Label(r4, text="🕐 更新日", style="Card.TLabel").pack(
            side="left", padx=(0, 4)
        )
        self.combo_date = ttk.Combobox(
            r4, textvariable=self.date_filter_var,
            values=["すべて", "今日", "過去7日", "過去30日", "過去1年"],
            state="readonly", style="App.TCombobox", width=10,
        )
        self.combo_date.pack(side="left", padx=(0, 16))

        ttk.Checkbutton(
            r4, text="📂 サブフォルダも検索",
            variable=self.subfolder_var, style="App.TCheckbutton",
        ).pack(side="left", padx=(0, 16))

        ttk.Checkbutton(
            r4, text="正規表現を使用",
            variable=self.regex_var, style="App.TCheckbutton",
        ).pack(side="left")

        ab = ttk.Frame(self.root, style="App.TFrame")
        ab.pack(fill="x", padx=px, pady=6)

        self.btn_search = ttk.Button(
            ab, text="🔍  検索する", style="Search.TButton",
            command=self._start_search,
        )
        self.btn_search.pack(side="left", padx=(0, 8))

        self.btn_cancel = ttk.Button(
            ab, text="⏹  キャンセル", style="Cancel.TButton",
            command=self._cancel_search, state="disabled",
        )
        self.btn_cancel.pack(side="left", padx=(0, 12))

        self.progress = ttk.Progressbar(
            ab, mode="indeterminate", length=180,
            style="App.Horizontal.TProgressbar",
        )
        self.progress.pack(side="left", padx=(4, 8), pady=2)

        self.status_label = ttk.Label(ab, text="", style="App.TLabel")
        self.status_label.pack(side="left", padx=4)

        th = ttk.Frame(self.root, style="App.TFrame")
        th.pack(fill="x", padx=px, pady=(6, 2))
        ttk.Label(
            th, text="📋 検索結果", style="App.TLabel",
            font=(self.FONT_FAMILY, 10, "bold"),
        ).pack(side="left")
        self.count_label = ttk.Label(th, text="0 件", style="Count.TLabel")
        self.count_label.pack(side="left", padx=(8, 0))

        columns = ("name", "folder", "size", "modified")
        col_headings = {
            "name": "📄 ファイル名",
            "folder": "📁 フォルダ",
            "size": "💾 サイズ",
            "modified": "🕐 更新日時",
        }
        col_widths = {"name": 230, "folder": 350, "size": 100, "modified": 170}

        tf = ttk.Frame(self.root, style="App.TFrame")
        tf.pack(fill="both", expand=True, padx=px, pady=(0, 8))

        self.tree = ttk.Treeview(
            tf, columns=columns, show="headings",
            selectmode="browse", style="App.Treeview",
        )
        for col in columns:
            self.tree.heading(
                col, text=col_headings[col],
                command=lambda c=col: self._sort_by_column(c),
            )
            anchor = "e" if col == "size" else "w"
            self.tree.column(col, width=col_widths[col], anchor=anchor)

        self.tree.tag_configure("odd", background=C["ROW_ODD"])
        self.tree.tag_configure("even", background=C["ROW_EVEN"])

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tf.columnconfigure(0, weight=1)
        tf.rowconfigure(0, weight=1)

        self.tree.bind("<Double-1>", self._open_selected_file)

        ft = ttk.Frame(self.root, style="App.TFrame")
        ft.pack(fill="x", padx=px, pady=(0, 8))
        dnd_hint = " ｜ フォルダをドラッグ&ドロップで指定可能" if HAS_WINDND else ""
        ttk.Label(
            ft,
            text=f"💡 ダブルクリック: 開く ｜ 右クリック: メニュー ｜ ヘッダー: ソート{dnd_hint}",
            style="Count.TLabel",
        ).pack(side="left")

    def _build_context_menu(self):
        self.ctx_menu = Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(
            label="📂 ファイルを開く", command=self._ctx_open_file
        )
        self.ctx_menu.add_command(
            label="📁 フォルダを開く", command=self._ctx_open_folder
        )
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(
            label="📋 ファイルパスをコピー", command=self._ctx_copy_path
        )
        self.ctx_menu.add_command(
            label="📋 フォルダパスをコピー", command=self._ctx_copy_folder_path
        )
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(
            label="🗑️ ファイルを削除", command=self._ctx_delete_file
        )

        self.tree.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.ctx_menu.post(event.x_root, event.y_root)

    def _get_selected_path(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        v = self.tree.item(sel[0], "values")
        return os.path.join(v[1], v[0])

    def _ctx_open_file(self):
        p = self._get_selected_path()
        if p and os.path.isfile(p):
            try:
                os.startfile(p)
            except OSError as e:
                messagebox.showerror("エラー", str(e))

    def _ctx_open_folder(self):
        sel = self.tree.selection()
        if sel:
            folder = self.tree.item(sel[0], "values")[1]
            if os.path.isdir(folder):
                os.startfile(folder)

    def _ctx_copy_path(self):
        p = self._get_selected_path()
        if p:
            self.root.clipboard_clear()
            self.root.clipboard_append(p)

    def _ctx_copy_folder_path(self):
        sel = self.tree.selection()
        if sel:
            folder = self.tree.item(sel[0], "values")[1]
            self.root.clipboard_clear()
            self.root.clipboard_append(folder)

    def _ctx_delete_file(self):
        p = self._get_selected_path()
        if not p or not os.path.isfile(p):
            return
        if messagebox.askyesno("確認", f"本当に削除しますか？\n{p}"):
            try:
                os.remove(p)
                sel = self.tree.selection()
                if sel:
                    self.tree.delete(sel[0])
                    self._reapply_row_tags()
                    total = len(self.tree.get_children(""))
                    self.count_label.config(text=f"{total} 件")
            except OSError as e:
                messagebox.showerror("エラー", str(e))

    def _setup_drag_and_drop(self):
        if not HAS_WINDND:
            return
        windnd.hook_dropfiles(self.root, func=self._on_drop)

    def _on_drop(self, files):
        if not files:
            return
        path = files[0]
        if isinstance(path, bytes):
            path = path.decode("utf-8", errors="replace")
        if os.path.isdir(path):
            self.folder_var.set(path)
        elif os.path.isfile(path):
            self.folder_var.set(os.path.dirname(path))

    @staticmethod
    def _load_history() -> list[str]:
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data[:MAX_HISTORY]
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return []

    def _save_history(self, keyword: str):
        if not keyword:
            return
        if keyword in self._history:
            self._history.remove(keyword)
        self._history.insert(0, keyword)
        self._history = self._history[:MAX_HISTORY]
        self.combo_keyword.config(values=self._history)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False)
        except OSError:
            pass

    def _browse_folder(self):
        path = filedialog.askdirectory(title="検索するフォルダを選択")
        if path:
            self.folder_var.set(path)

    def _start_search(self):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("入力エラー", "有効なフォルダを指定してください。")
            return

        keyword = self.keyword_var.get().strip()

        if not keyword and not self.ext_var.get().strip():
            messagebox.showwarning(
                "入力エラー",
                "ファイル名または拡張子のどちらかを入力してください。",
            )
            return

        if self.regex_var.get() and keyword:
            try:
                re.compile(keyword)
            except re.error as e:
                messagebox.showerror("正規表現エラー", f"無効な正規表現です:\n{e}")
                return

        ext_text = self.ext_var.get().strip()
        extensions: list[str] = []
        if ext_text:
            extensions = [
                e.strip().lower() if e.strip().startswith(".")
                else f".{e.strip().lower()}"
                for e in ext_text.split(",") if e.strip()
            ]

        min_mtime = self._calc_min_mtime()

        self._save_history(keyword)

        self._clear_results()
        self._cancel_event.clear()
        self._set_searching(True)

        self._search_thread = threading.Thread(
            target=self._search_worker,
            args=(folder, keyword, self.regex_var.get(),
                  extensions, self.subfolder_var.get(), min_mtime),
            daemon=True,
        )
        self._search_thread.start()
        self._poll_results()

    def _cancel_search(self):
        self._cancel_event.set()

    def _open_selected_file(self, _event):
        p = self._get_selected_path()
        if p and os.path.isfile(p):
            try:
                os.startfile(p)
            except OSError as e:
                messagebox.showerror("エラー", str(e))

    def _calc_min_mtime(self) -> float | None:
        choice = self.date_filter_var.get()
        now = datetime.datetime.now()
        if choice == "今日":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return start.timestamp()
        elif choice == "過去7日":
            return (now - datetime.timedelta(days=7)).timestamp()
        elif choice == "過去30日":
            return (now - datetime.timedelta(days=30)).timestamp()
        elif choice == "過去1年":
            return (now - datetime.timedelta(days=365)).timestamp()
        return None

    def _sort_by_column(self, col: str):
        reverse = self._sort_reverse.get(col, False)
        self._sort_reverse[col] = not reverse

        items = [(self.tree.set(iid, col), iid)
                 for iid in self.tree.get_children("")]

        if col == "size":
            items.sort(key=lambda x: self._parse_size(x[0]), reverse=reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=reverse)

        for idx, (_, iid) in enumerate(items):
            self.tree.move(iid, "", idx)
        self._reapply_row_tags()

    @staticmethod
    def _parse_size(text: str) -> float:
        units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
        text = text.strip()
        for unit, factor in units.items():
            if text.upper().endswith(unit):
                try:
                    return float(text[:-len(unit)].strip()) * factor
                except ValueError:
                    return 0
        return 0

    def _search_worker(
        self, folder: str, keyword: str, use_regex: bool,
        extensions: list[str], recurse: bool, min_mtime: float | None,
    ):
        pattern = None
        if use_regex and keyword:
            pattern = re.compile(keyword, re.IGNORECASE)

        try:
            if recurse:
                walker = os.walk(folder)
            else:
                try:
                    entries = os.listdir(folder)
                except PermissionError:
                    self._result_queue.put(("__DONE__",))
                    return
                files = [e for e in entries if os.path.isfile(os.path.join(folder, e))]
                walker = [(folder, [], files)]

            for dirpath, _dirs, filenames in walker:
                if self._cancel_event.is_set():
                    self._result_queue.put(("__CANCELLED__",))
                    return

                for fname in filenames:
                    if self._cancel_event.is_set():
                        self._result_queue.put(("__CANCELLED__",))
                        return

                    if extensions:
                        _, ext = os.path.splitext(fname)
                        if ext.lower() not in extensions:
                            continue

                    if keyword:
                        if pattern:
                            if not pattern.search(fname):
                                continue
                        else:
                            if keyword.lower() not in fname.lower():
                                continue

                    full_path = os.path.join(dirpath, fname)
                    try:
                        stat = os.stat(full_path)
                    except OSError:
                        continue

                    if min_mtime is not None and stat.st_mtime < min_mtime:
                        continue

                    size = self._format_size(stat.st_size)
                    mtime = datetime.datetime.fromtimestamp(
                        stat.st_mtime
                    ).strftime("%Y-%m-%d %H:%M:%S")

                    self._result_queue.put((fname, dirpath, size, mtime))
        except PermissionError:
            pass

        self._result_queue.put(("__DONE__",))

    @staticmethod
    def _format_size(n: int) -> str:
        if n < 1024:
            return f"{n} B"
        elif n < 1024**2:
            return f"{n/1024:.1f} KB"
        elif n < 1024**3:
            return f"{n/1024**2:.1f} MB"
        else:
            return f"{n/1024**3:.2f} GB"

    def _poll_results(self):
        while True:
            try:
                item = self._result_queue.get_nowait()
            except queue.Empty:
                break

            if item[0] == "__DONE__":
                self._set_searching(False)
                total = len(self.tree.get_children(""))
                self.status_label.config(
                    text=f"✅ 完了 — {total} 件", style="StatusOK.TLabel",
                )
                self.count_label.config(text=f"{total} 件")
                return
            elif item[0] == "__CANCELLED__":
                self._set_searching(False)
                total = len(self.tree.get_children(""))
                self.status_label.config(
                    text=f"⏹ キャンセル — {total} 件", style="App.TLabel",
                )
                self.count_label.config(text=f"{total} 件")
                return
            else:
                tag = "even" if self._row_count % 2 == 0 else "odd"
                self.tree.insert("", END, values=item, tags=(tag,))
                self._row_count += 1

        total = len(self.tree.get_children(""))
        self.status_label.config(
            text=f"🔍 検索中… {total} 件", style="StatusSearch.TLabel",
        )
        self.count_label.config(text=f"{total} 件")
        self.root.after(self.POLL_INTERVAL_MS, self._poll_results)

    def _clear_results(self):
        for iid in self.tree.get_children(""):
            self.tree.delete(iid)
        self._row_count = 0
        self.count_label.config(text="0 件")
        self.status_label.config(text="", style="App.TLabel")

    def _set_searching(self, active: bool):
        if active:
            self.btn_search.config(state="disabled")
            self.btn_cancel.config(state="normal")
            self.progress.start(10)
            self.status_label.config(
                text="🔍 検索中…", style="StatusSearch.TLabel",
            )
        else:
            self.btn_search.config(state="normal")
            self.btn_cancel.config(state="disabled")
            self.progress.stop()

    def _reapply_row_tags(self):
        for idx, iid in enumerate(self.tree.get_children("")):
            self.tree.item(iid, tags=("even" if idx % 2 == 0 else "odd",))

def main():
    root = Tk()
    FileSearchApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
