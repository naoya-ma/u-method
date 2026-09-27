import flet as ft

from services import theme_repo


def show_item_form_dialog(
    page: ft.Page,
    title: str,
    fields: list[dict],
    initial: dict | None,
    on_submit,
    on_delete=None,
    width: int = 480,
    on_preview=None,
) -> None:
    """
    ジョブ／ツール／リンク／APIキー共通の追加・編集ダイアログ。

    fields: [{"key": str, "label": str,
              "type": "text"|"password"|"checkbox"|"dropdown"|"readonly_text",
              "options": list[str] (dropdown用), "hint": str, "tooltip": str,
              "multiline": bool, "autofocus": bool, "wide": bool,
              "min_lines": int, "max_lines": int}]
    "wide": True の項目は、行全体（他の項目の2倍幅）を使う複数行入力欄になり、
    既定では3行分の高さ（"min_lines"/"max_lines"を指定すると変更できる。省略時は"min_lines"と同じ値）で、
    それを超える入力は内部スクロールで表示する。"wide"でない項目は2つずつ横に並べる。
    ダイアログ全体の横幅は`width`引数で指定する
    initial: 編集時の既存値（新規追加時は None）
    on_submit(values: dict) を「保存」押下時に呼び出す
    on_delete() を指定した場合のみ「削除」ボタンを表示する
    on_preview(values: dict) を指定した場合のみ「プレビュー」ボタンを表示する。
    このダイアログは閉じずに、その時点の入力内容を渡す（保存はしない）
    """
    initial = initial or {}
    inputs: dict[str, ft.Control] = {}
    rows: list[ft.Control] = []
    pending_pair: list[ft.Control] = []

    def flush_pending() -> None:
        if pending_pair:
            rows.append(ft.Row(controls=list(pending_pair), spacing=12))
            pending_pair.clear()

    for f in fields:
        key = f["key"]
        label = f.get("label", key)
        ftype = f.get("type", "text")
        value = initial.get(key, f.get("default", ""))
        tooltip = f.get("tooltip")
        autofocus = f.get("autofocus", False)
        wide = f.get("wide", False)

        if ftype == "checkbox":
            ctl = ft.Checkbox(label=label, value=bool(value), tooltip=tooltip, autofocus=autofocus)
        elif ftype == "dropdown":
            ctl = ft.Dropdown(
                label=label,
                value=value or None,
                options=[ft.DropdownOption(key=o, text=o) for o in f.get("options", [])],
                tooltip=tooltip,
                autofocus=autofocus,
            )
        elif ftype == "password":
            ctl = ft.TextField(
                label=label,
                value="",
                password=True,
                can_reveal_password=True,
                hint_text=f.get("hint", ""),
                tooltip=tooltip,
                autofocus=autofocus,
            )
        elif ftype == "readonly_text":
            ctl = ft.TextField(
                label=label,
                value=str(value) if value is not None else "",
                read_only=True,
                tooltip=tooltip,
            )
        elif wide:
            # 他の項目の2倍幅（行全体）の入力欄。既定は複数行（3行分の高さ、"min_lines"/"max_lines"で
            # 個別指定可、それを超える分は内部スクロール）。"multiline": False を渡すと単一行のまま
            # 横幅だけダイアログ全体に広げる（例: コマンド欄）。
            # 明示的に`width`を指定する（`ft.Column`の子は既定でcross-axis中央寄せになり、
            # 指定しないと横幅いっぱいに広がらず内容によって小さく表示されてしまう）
            multiline = f.get("multiline", True)
            lines = f.get("min_lines", 3)
            ctl = ft.TextField(
                label=label,
                value=str(value) if value is not None else "",
                multiline=multiline,
                min_lines=lines if multiline else None,
                max_lines=f.get("max_lines", lines) if multiline else 1,
                tooltip=tooltip,
                autofocus=autofocus,
                width=width,
            )
        else:
            ctl = ft.TextField(
                label=label,
                value=str(value) if value is not None else "",
                multiline=f.get("multiline", False),
                tooltip=tooltip,
                autofocus=autofocus,
            )

        inputs[key] = ctl

        if wide:
            flush_pending()
            rows.append(ctl)
        else:
            ctl.expand = 1
            pending_pair.append(ctl)
            if len(pending_pair) == 2:
                flush_pending()

    flush_pending()
    controls = rows

    def collect_values() -> dict:
        values = {}
        for key, ctl in inputs.items():
            values[key] = ctl.value if isinstance(ctl, ft.Checkbox) else (ctl.value or "")
        return values

    def handle_ok(e: ft.ControlEvent) -> None:
        values = collect_values()
        page.pop_dialog()
        on_submit(values)

    def handle_cancel(e: ft.ControlEvent) -> None:
        page.pop_dialog()

    def handle_delete(e: ft.ControlEvent) -> None:
        page.pop_dialog()
        on_delete()

    def handle_preview(e: ft.ControlEvent) -> None:
        on_preview(collect_values())

    actions = [
        ft.TextButton("キャンセル", on_click=handle_cancel, tooltip="変更を破棄して閉じる"),
    ]
    if on_preview:
        actions.append(
            ft.TextButton(
                "プレビュー",
                on_click=handle_preview,
                tooltip="現在の入力内容をプレビュー表示する（保存はしない）",
            )
        )
    if on_delete:
        actions.append(
            ft.TextButton(
                "削除",
                on_click=handle_delete,
                tooltip="この項目を削除する",
                style=ft.ButtonStyle(color=theme_repo.error_color()),
            )
        )
    actions.append(ft.Button("保存", on_click=handle_ok, tooltip="入力内容を保存する"))

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Column(controls=controls, tight=True, width=width, scroll=ft.ScrollMode.AUTO),
        actions=actions,
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)
