def safe_update(control) -> None:
    """
    まだページに追加されていないコントロールに対する update() を安全に無視する。
    （コンストラクタ内で初期一覧を描画する際、page.add() 前に呼ばれるケースがあるため）
    """
    try:
        control.page
    except RuntimeError:
        return
    control.update()
