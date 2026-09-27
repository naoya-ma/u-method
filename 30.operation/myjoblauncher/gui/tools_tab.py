import os

import flet as ft

from gui.confirm_dialog import show_script_confirm_dialog
from gui.icon_grid_view import (
    RECOMMEND_OPTIONS,
    GridEntry,
    build_icon_grid,
    build_list_view,
    build_sort_mode_dropdown,
    build_view_mode_toggle,
    parse_recommend,
    sort_items,
)
from gui.item_form_dialog import show_item_form_dialog
from gui.parameter_dialog import show_parameter_dialog
from gui.safe_update import safe_update
from gui.toast import show_toast
from services.execution_engine import (
    is_terminal_command,
    start_script_process,
    start_terminal_process,
    start_tool,
    stream_process,
)
from services.tools_repo import (
    SCRIPT_KIND_BATCH,
    SCRIPT_KIND_EXTENSIONS,
    SCRIPT_KIND_NORMAL,
    SCRIPT_KINDS,
    ToolItem,
    load_tools,
    save_tools,
)
from services.keyboard_shortcut import send_win_shortcut
from services import applog, icon_cache, path_utils, search_history_repo, tz_repo, ui_log, view_mode_repo
from utils.param_parser import extract_params, substitute_params

TOOLS_PATH = "config/tools.toml"
VIEW_MODE_KEY = "tools_view_mode"
SORT_MODE_KEY = "tools_sort_mode"
SEARCH_HISTORY_KEY = "tools_search_history"

# コマンド欄は他の項目の約3倍幅（既定480pxでの半分幅ペア項目≈220pxの3倍）にするため単一行のwide項目にする
TOOLS_DIALOG_WIDTH = 700

TOOL_FIELDS = [
    {"key": "name", "label": "ツール名", "type": "text"},
    {
        "key": "command",
        "label": (
            "起動コマンド（exeのパスなど。Windowsキー操作は shortcut:win+r 等。"
            "バッチ/PowerShellスクリプトの場合は複数行入力可、コメント行〈:: や #〉も書けます。"
            "{{param}} で実行時入力欄を追加できます）"
        ),
        "type": "text",
        "wide": True,
        "min_lines": 3,
        "max_lines": 10,
    },
    {
        "key": "script_kind",
        "label": "実行種別",
        "type": "dropdown",
        "options": list(SCRIPT_KINDS),
        "default": SCRIPT_KIND_NORMAL,
        "tooltip": "バッチ/PowerShellスクリプトを選ぶと、実行前に内容確認ダイアログを表示し、結果を運用ログへ出力します",
    },
    {"key": "working_dir", "label": "作業ディレクトリ（省略可）", "type": "text"},
    {"key": "args", "label": "引数（省略可、通常コマンドのみ）", "type": "text"},
    {
        "key": "icon_source_path",
        "label": "アイコン取得用パス（省略可。例: C:\\Windows\\System32\\winver.exe）",
        "type": "text",
        "tooltip": "コマンドからアイコンを自動解決できない場合に、アイコン抽出元のexeパスを直接指定します",
    },
    {"key": "category", "label": "カテゴリ", "type": "text"},
    {
        "key": "recommend",
        "label": "おすすめ（1〜5、空欄で未設定）",
        "type": "dropdown",
        # 下(先頭)から1、上(末尾)にいくほど5になるよう、選択肢は降順で渡す（job_editorのmaturityと同じ規約）
        "options": list(reversed(RECOMMEND_OPTIONS)),
    },
    {"key": "comment", "label": "ひとこと", "type": "text"},
    {"key": "note", "label": "備考", "type": "text"},
]


def _format_last_used(item: ToolItem) -> str:
    return item.last_used_at.replace("T", " ")[:16] if item.last_used_at else "未実行"


def _collapse_tool_values(values: dict) -> dict:
    """
    保存前に、作業ディレクトリ・アイコン取得用パス・（通常コマンドの場合のみ）起動コマンドに含まれる
    絶対パスを環境変数トークンへ置き換える（`services/path_utils.collapse_path()`、ユーザー指定の
    優先順位）。バッチ/PowerShellスクリプトのコマンド欄は複数行のスクリプト本文であり単純な
    パスではないため対象外にする
    """
    values = dict(values)
    values["working_dir"] = path_utils.collapse_path(values.get("working_dir", ""))
    values["icon_source_path"] = path_utils.collapse_path(values.get("icon_source_path", ""))
    if (values.get("script_kind") or SCRIPT_KIND_NORMAL) == SCRIPT_KIND_NORMAL:
        values["command"] = path_utils.collapse_path(values.get("command", ""))
    return values


def _matches_search(item: ToolItem, query: str) -> bool:
    """
    コマンド欄の検索キーワードでツールを絞り込む。先頭の"/"は付けても付けなくても同じ扱いにする
    （"/vscode"でも"vscode"でも動く）。名前・コマンド（パス）・カテゴリのいずれかに大文字小文字を
    無視した部分一致があれば真とする（例: "/vscode"→名前一致、"/microsoft"→カテゴリ
    "Microsoftアプリ"に一致、"/エディタ"→カテゴリ"エディター"に部分一致、"/web"→カテゴリ
    "Webブラウザー"に一致）。空欄（"/"のみ含む）は常に真（絞り込みなし）
    """
    keyword = query[1:] if query.startswith("/") else query
    keyword = keyword.strip().lower()
    if not keyword:
        return True
    haystacks = (item.name, item.command, item.category)
    return any(keyword in (h or "").lower() for h in haystacks)


def _command_summary(item: ToolItem) -> str:
    """一覧・ツールチップ表示用。バッチ/PowerShellスクリプト（複数行）は先頭行のみ＋省略記号にする"""
    lines = item.command.splitlines()
    first_line = lines[0] if lines else ""
    if item.script_kind != SCRIPT_KIND_NORMAL and len(lines) > 1:
        return f"{first_line} …"
    return first_line


class ToolsTab:
    """
    よく使うツールタブ。登録済みコマンドをワンクリックで起動する（実行履歴には残さない）。
    アイコン表示（大/中/小）・一覧表示を切り替え可能（既定はアイコン表示・中）。
    一覧は使用回数/名前/最終実行日時で並び替え可能（既定は使用回数の多い順）
    """

    def __init__(self, page: ft.Page):
        self.page = page
        self.tools: list[ToolItem] = load_tools(TOOLS_PATH)
        self.view_mode = view_mode_repo.load_view_mode(VIEW_MODE_KEY)
        self.sort_mode = view_mode_repo.load_sort_mode(SORT_MODE_KEY)
        self.search_query = ""
        self.search_history: list[str] = search_history_repo.load_history(SEARCH_HISTORY_KEY)
        self.body = ft.Container(expand=True, border=ft.Border.all(1, ft.Colors.OUTLINE))
        self.sort_dropdown = build_sort_mode_dropdown(self.sort_mode, self._handle_sort_mode_change)
        self.toggle_row = build_view_mode_toggle(self.view_mode, self._handle_view_mode_change)

        self.search_field = ft.TextField(
            label="コマンド",
            hint_text="/vscode のように検索",
            expand=3,  # ユーザーからの要望: 行内の可変幅（後述spacerとの合計）の3/4を占めるようにする
            dense=True,
            on_change=self._handle_search_change,
            on_submit=self._handle_search_submit,
        )
        self.history_button = ft.PopupMenuButton(
            icon=ft.Icons.HISTORY,
            tooltip="検索履歴（最大20件）",
            items=self._build_history_items(),
        )
        # ✅ build_view_mode_toggle()は呼ぶたびに新しいft.Rowを返すため、title_row.controlsを
        # インデックスで直接差し替えるのではなく、中身が入れ替わらない箱（toggle_container）を
        # 用意し、その.controlsだけを差し替える（title_row内の並び順を変更してもインデックスが
        # ずれて事故らないようにするため）
        self.toggle_container = ft.Row(controls=[self.toggle_row])
        self.title_row = ft.Row(
            # ✅【実機で確認済み・撤去済み】ここに wrap=True を付ける案を一度試したが、
            # Flet 1.0.1では wrap=True の ft.Row（Flutter Wrapベース）は子の expand
            # （flex拡張）に対応しておらず、search_field(expand=3) を含む行全体が
            # 描画自体されなくなる（例外もログに出ず、画面上は空白のグレー領域になるだけ、
            # という気付きにくい壊れ方をする）。wrap と expand は併用しないこと
            controls=[
                ft.Text("よく使うツール", weight=ft.FontWeight.BOLD),
                ft.Container(width=16),
                self.search_field,
                self.history_button,
                ft.Container(expand=True),  # search_field(expand=3)との組で3:1、可変幅の3/4をコマンド欄が占める
                self.sort_dropdown,
                self.toggle_container,
                ft.Button(
                    "追加", icon=ft.Icons.ADD, tooltip="新しいツールを追加する", on_click=self._add
                ),
            ]
        )

        self.view = ft.Column(
            expand=True,
            # ✅ horizontal_alignment未指定（既定START）だと子（title_row/body）が内在サイズで
            # 左詰めになり、Column自体はexpand=Trueで全幅確保していてもtitle_rowはそこまで
            # 広がらない（CLAUDE.md「ft.Columnの子はexpandだけでは横幅いっぱいに広がらない」の
            # 既知の挙動）。STRETCHにしてtitle_row/bodyともColumn幅いっぱいに広げることで、
            # title_row内のsearch_field(expand=3)が実際に効く可変幅を確保する
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                self.title_row,
                self.body,
            ],
        )

        self._refresh()

    # ========================
    # ✅ コマンド欄（/キーワード検索）
    # ========================
    def _build_history_items(self) -> list[ft.PopupMenuItem]:
        if not self.search_history:
            return [ft.PopupMenuItem(content="履歴はありません", disabled=True)]
        return [
            ft.PopupMenuItem(content=query, on_click=self._make_history_select_handler(query))
            for query in self.search_history
        ]

    def _make_history_select_handler(self, query: str):
        def handler(e: ft.ControlEvent) -> None:
            self.search_field.value = query
            self.search_query = query
            safe_update(self.search_field)
            self._refresh()

        return handler

    def _handle_search_change(self, e: ft.ControlEvent) -> None:
        self.search_query = e.control.value or ""
        self._refresh()

    def _handle_search_submit(self, e: ft.ControlEvent) -> None:
        self.search_history = search_history_repo.add_to_history(self.search_query, self.search_history)
        search_history_repo.save_history(SEARCH_HISTORY_KEY, self.search_history)
        self.history_button.items = self._build_history_items()
        safe_update(self.history_button)

    # ========================
    # ✅ 表示モード切替
    # ========================
    def _handle_view_mode_change(self, mode: str) -> None:
        self.view_mode = mode
        view_mode_repo.save_view_mode(VIEW_MODE_KEY, mode)
        self.toggle_row = build_view_mode_toggle(self.view_mode, self._handle_view_mode_change)
        self.toggle_container.controls = [self.toggle_row]
        safe_update(self.view)
        self._refresh()

    # ========================
    # ✅ 並び替え
    # ========================
    def _handle_sort_mode_change(self, mode: str) -> None:
        self.sort_mode = mode
        view_mode_repo.save_sort_mode(SORT_MODE_KEY, mode)
        self._refresh()

    # ========================
    # ✅ 描画
    # ========================
    def _refresh(self) -> None:
        filtered = [item for item in self.tools if _matches_search(item, self.search_query)]
        ordered = sort_items(filtered, self.sort_mode)

        entries = [
            GridEntry(
                label=item.name,
                subtitle=_command_summary(item),
                last_used_label=_format_last_used(item),
                icon_path=icon_cache.get_tool_icon_path(item),
                fallback_icon=icon_cache.guess_fallback_icon(item.name),
                on_launch=self._make_run_handler(item),
                on_edit=self._make_edit_handler(item),
                tooltip=f"クリックするとツールを呼出します\n({_command_summary(item)})",
                category=item.category,
                pinned=item.pinned,
                on_toggle_pin=self._make_pin_handler(item),
            )
            for item in ordered
        ]

        if self.view_mode == "list":
            self.body.content = build_list_view(entries)
        else:
            self.body.content = build_icon_grid(entries, self.view_mode)

        safe_update(self.body)

    def _make_run_handler(self, item: ToolItem):
        def handler() -> None:
            if item.script_kind != SCRIPT_KIND_NORMAL:
                self._run_script_tool(item)
                return

            try:
                if item.command.startswith("shortcut:"):
                    send_win_shortcut(item.command.split(":", 1)[1])
                elif is_terminal_command(item.command):
                    start_terminal_process(item.command, item.args, item.working_dir)
                else:
                    start_tool(item.command, item.args, item.working_dir)

                item.use_count += 1
                item.last_used_at = tz_repo.now().isoformat()
                save_tools(TOOLS_PATH, self.tools)
                icon_cache.get_tool_icon_path(item, force=True)
                ui_log.log_action("ツール", "launch", item.name)
                applog.log(
                    "INFO",
                    f"コマンドを実行しました。File={item.command}",
                    func_name=f"ツール:{item.name}",
                )
                self._refresh()
            except Exception as ex:
                show_toast(self.page, f"起動に失敗しました: {ex}")

        return handler

    # ========================
    # ✅ バッチ/PowerShellスクリプトの実行
    # {{param}}入力（あれば）→内容確認ダイアログ→捕捉実行→運用ログへ出力、という流れ。
    # 通常コマンドの起動（start_tool等、切り離し実行で出力を見ない）とは別経路にしている
    # ========================
    def _run_script_tool(self, item: ToolItem) -> None:
        params = extract_params(item.command)

        if params:

            def on_submit(values: dict[str, str]) -> None:
                resolved = substitute_params(item.command, values)
                self._confirm_script(item, resolved)

            show_parameter_dialog(self.page, params, on_submit)
            return

        self._confirm_script(item, item.command)

    def _confirm_script(self, item: ToolItem, content: str) -> None:
        show_script_confirm_dialog(
            self.page,
            item.name,
            item.script_kind,
            content,
            on_confirm=lambda: self._execute_script(item, content),
        )

    def _execute_script(self, item: ToolItem, content: str) -> None:
        ui_log.log_action("ツール", "execute", item.name)
        show_toast(self.page, f"「{item.name}」を実行しています…（結果は運用ログに出力されます）")
        self.page.run_thread(self._run_script_thread, item, content)

    def _run_script_thread(self, item: ToolItem, content: str) -> None:
        extension = SCRIPT_KIND_EXTENSIONS.get(item.script_kind, ".bat")
        func_name = f"ツール:{item.name}"

        def on_output(line: str) -> None:
            text = line.rstrip()
            is_error = text.startswith("[ERR]")
            applog.log("ERROR" if is_error else "INFO", text, func_name=func_name)

        kind_label = "バッチ" if item.script_kind == SCRIPT_KIND_BATCH else "スクリプト"

        temp_path = None
        try:
            process, temp_path = start_script_process(extension, content, item.working_dir or None)
            applog.log("INFO", f"{kind_label}を実行しました。File={temp_path}", func_name=func_name)
            stream_process(process, on_output)
            returncode = process.returncode
            applog.log(
                "ERROR" if returncode != 0 else "INFO",
                f"「{item.name}」の実行が終了しました（return={returncode}）",
                func_name=func_name,
            )
        except Exception as ex:
            applog.log("ERROR", f"「{item.name}」の実行に失敗しました: {ex}", func_name=func_name)
        finally:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        item.use_count += 1
        item.last_used_at = tz_repo.now().isoformat()
        save_tools(TOOLS_PATH, self.tools)
        self._refresh()
        show_toast(self.page, f"「{item.name}」を実行しました。結果はログを確認してください。")

    def _make_pin_handler(self, item: ToolItem):
        def handler() -> None:
            item.pinned = not item.pinned
            ui_log.log_action("ツール", "toggle", item.name, value="pinned" if item.pinned else "unpinned")
            self._persist("ピン止めしました" if item.pinned else "ピン止めを解除しました")

        return handler

    def _add(self, e: ft.ControlEvent) -> None:
        def on_submit(values: dict) -> None:
            values = _collapse_tool_values(values)
            new_item = ToolItem(
                name=values["name"],
                command=values["command"],
                working_dir=values.get("working_dir", ""),
                args=values.get("args", ""),
                note=values.get("note", ""),
                category=values.get("category", ""),
                recommend=parse_recommend(values.get("recommend")),
                comment=values.get("comment", ""),
                script_kind=values.get("script_kind") or SCRIPT_KIND_NORMAL,
                icon_source_path=values.get("icon_source_path", ""),
            )
            self.tools.append(new_item)
            icon_cache.get_tool_icon_path(new_item, force=True)
            ui_log.log_action("ツール", "add", values["name"])
            self._persist(self._save_message("ツールを追加しました", new_item))

        show_item_form_dialog(self.page, "ツールを追加", TOOL_FIELDS, None, on_submit, width=TOOLS_DIALOG_WIDTH)

    def _make_edit_handler(self, item: ToolItem):
        def handler() -> None:
            initial = {
                "name": item.name,
                "command": item.command,
                "working_dir": item.working_dir,
                "args": item.args,
                "category": item.category,
                "recommend": str(item.recommend) if item.recommend else "",
                "comment": item.comment,
                "note": item.note,
                "script_kind": item.script_kind,
                "icon_source_path": item.icon_source_path,
            }

            def on_submit(values: dict) -> None:
                values = _collapse_tool_values(values)
                item.name = values["name"]
                item.command = values["command"]
                item.working_dir = values.get("working_dir", "")
                item.args = values.get("args", "")
                item.category = values.get("category", "")
                item.recommend = parse_recommend(values.get("recommend"))
                item.comment = values.get("comment", "")
                item.note = values.get("note", "")
                item.script_kind = values.get("script_kind") or SCRIPT_KIND_NORMAL
                item.icon_source_path = values.get("icon_source_path", "")
                icon_cache.get_tool_icon_path(item, force=True)
                ui_log.log_action("ツール", "edit", item.name)
                self._persist(self._save_message("ツールを更新しました", item))

            def on_delete() -> None:
                name = item.name
                self.tools.remove(item)
                ui_log.log_action("ツール", "delete", name)
                self._persist("ツールを削除しました")

            show_item_form_dialog(
                self.page,
                f"ツールを編集: {item.name}",
                TOOL_FIELDS,
                initial,
                on_submit,
                on_delete,
                width=TOOLS_DIALOG_WIDTH,
            )

        return handler

    def _save_message(self, base_message: str, item: ToolItem) -> str:
        """
        `icon_source_path`が設定されているのに実在しない場合、保存完了メッセージに警告を添える
        （誤入力に気付けるよう。従来は失敗が画面に一切現れず「アイコンが更新されない」としか
        見えなかったため）
        """
        if icon_cache.icon_source_path_missing(item.icon_source_path):
            return f"{base_message}（アイコン取得用パスが見つかりません。パスを確認してください）"
        return base_message

    def _persist(self, message: str) -> None:
        save_tools(TOOLS_PATH, self.tools)
        self._refresh()
        show_toast(self.page, message)
