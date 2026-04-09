"""Streamlit GUI for office-agent.

Launch via:
    office_agent gui
    streamlit run office_agent/gui.py
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
from pathlib import Path

import streamlit as st

from office_agent.config import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DOC_TYPE_MAP = {
    "自動": None,
    "Word": "docx",
    "Excel": "xlsx",
    "PowerPoint": "pptx",
}

_PROGRESS_MSGS: dict[str, tuple[str, float]] = {
    "stage1_start": ("① AI プランニング中...", 0.10),
    "stage1_done":  ("① AI プランニング完了",  0.33),
    "stage2_start": ("② プラン検証中...",       0.40),
    "stage2_done":  ("② プラン検証完了",        0.66),
    "stage3_start": ("③ ファイル生成中...",      0.70),
    "stage3_done":  ("③ ファイル生成完了",       1.00),
}

_STAGE_LABELS = {
    "stage1": "① AI プランニング",
    "stage2": "② プラン検証",
    "stage3": "③ ファイル生成",
}

_FILE_ICONS = {".docx": "📝", ".xlsx": "📊", ".pptx": "📑"}

_FILE_TYPE_LABELS = {
    ".docx": "Word 文書",
    ".xlsx": "Excel ファイル",
    ".pptx": "PowerPoint ファイル",
}

_EXAMPLE_TASKS = [
    ("📝 Word 報告書", "月次営業報告書をWordで作って"),
    ("📊 Excel 管理表", "売上管理表をExcelで作って"),
    ("📑 PowerPoint", "新人研修スライドを作って"),
    ("✉️ ビジネス文書", "取引先へのお詫び状を作って"),
]

# ---------------------------------------------------------------------------
# session_state の初期化
# ---------------------------------------------------------------------------

if "last_result" not in st.session_state:
    st.session_state.last_result = None   # dict | None
if "last_error" not in st.session_state:
    st.session_state.last_error = None    # Exception | None
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "task_input" not in st.session_state:
    st.session_state.task_input = ""
if "task_input_widget" not in st.session_state:
    st.session_state.task_input_widget = st.session_state.task_input

# クリア要求を widget 生成前に処理
if st.session_state.get("_clear_pending"):
    st.session_state.task_input_widget = ""
    del st.session_state["_clear_pending"]

# サンプル入力の設定を widget 生成前に処理
if st.session_state.get("_fill_pending"):
    st.session_state.task_input_widget = st.session_state["_fill_pending"]
    del st.session_state["_fill_pending"]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _friendly_error(exc: Exception) -> tuple[str, str]:
    """(タイトル, 対処法) を返す。"""
    from office_agent.llm.exceptions import (
        LLMConnectionError, LLMTimeoutError,
        LLMBadResponseError, LLMJSONDecodeError,
    )
    import pydantic

    if isinstance(exc, LLMConnectionError):
        return (
            "Ollama に接続できません",
            "`ollama serve` でサーバを起動してください",
        )
    if isinstance(exc, LLMTimeoutError):
        return (
            "応答がタイムアウトしました",
            "Ollama サーバが高負荷の可能性があります。しばらく待ってから再試行してください",
        )
    if isinstance(exc, (LLMBadResponseError, LLMJSONDecodeError)):
        return (
            "モデルからの応答が不正でした",
            "モデルを変更するか、タスクの説明を簡潔にして再試行してください",
        )
    if isinstance(exc, pydantic.ValidationError):
        return (
            "プラン検証エラー",
            "タスクの説明を具体的にして再試行してください",
        )
    if isinstance(exc, ValueError):
        return (
            f"検証エラー: {exc}",
            "タスクの説明をより具体的にして再試行してください",
        )
    return (f"{type(exc).__name__}: {exc}", "再試行するか、サイドバーの設定を確認してください")


def _build_stage_md(states: dict[str, str]) -> str:
    icons = {"pending": "⭕", "running": "🔄", "done": "✅"}
    suffixes = {"pending": "", "running": " — 実行中...", "done": " — 完了"}
    lines = []
    for key in ["stage1", "stage2", "stage3"]:
        s = states.get(key, "pending")
        lines.append(f"{icons[s]} **{_STAGE_LABELS[key]}**{suffixes[s]}")
    return "\n\n".join(lines)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.set_page_config(page_title="office-agent GUI", page_icon="📄", layout="wide")
st.title("📄 office-agent")
st.caption("自然言語から Word / Excel / PowerPoint を自動生成します")
st.divider()

with st.sidebar:
    st.header("⚙️ 設定")

    ollama_url = st.text_input(
        "Ollama URL",
        value="http://localhost:11434",
        help="Ollama サーバのURL",
    )
    model_name = st.text_input(
        "モデル名",
        value="llama3.1:8b",
        help="使用するOllamaモデル",
    )
    template_dir = st.text_input(
        "テンプレートディレクトリ",
        value="./templates",
        help="ドキュメントテンプレートのディレクトリ",
    )
    out_dir = st.text_input(
        "出力ディレクトリ",
        value="./out",
        help="生成ファイルの保存先",
    )

    st.divider()

    if st.button("🔌 接続確認", use_container_width=True):
        cfg = Config.from_env()
        cfg.ollama_url = ollama_url
        cfg.model = model_name
        try:
            from office_agent.llm.ollama import OllamaBackend
            health = OllamaBackend(cfg).check_health()
            if health["running"]:
                st.success(f"✅ Ollama 起動中: {ollama_url}")
                if health["model_available"]:
                    st.success(f"✅ モデル '{model_name}' 利用可能")
                else:
                    st.warning(
                        f"⚠️ モデル '{model_name}' が見つかりません\n"
                        f"`ollama pull {model_name}` で取得してください"
                    )
            else:
                st.error(
                    f"✗ Ollama に接続できません ({ollama_url})\n"
                    "`ollama serve` でサーバを起動してください"
                )
        except Exception as exc:
            st.error(f"接続確認エラー: {exc}")

# ---------------------------------------------------------------------------
# Main area — 入力セクション
# ---------------------------------------------------------------------------

st.subheader("📝 タスク入力")
st.caption("生成したい文書の内容を日本語で入力してください。下のボタンから例を選ぶこともできます。")

# サンプル入力ボタン（quick-fill）
ex_cols = st.columns(len(_EXAMPLE_TASKS))
for col, (label, example_text) in zip(ex_cols, _EXAMPLE_TASKS):
    with col:
        if st.button(label, use_container_width=True, disabled=st.session_state.is_running):
            st.session_state["_fill_pending"] = example_text
            st.rerun()

st.text_area(
    "タスク",
    key="task_input_widget",
    height=120,
    label_visibility="collapsed",
    placeholder=(
        "例: 「月次営業報告書をWordで作って」\n"
        "    「売上管理表をExcelで作って」\n"
        "    「新人研修スライドをPowerPointで作って」\n"
        "    「取引先へのお詫び状を作って」"
    ),
    help="生成したいドキュメントの説明を日本語で入力してください",
)

doc_type_label = st.selectbox(
    "出力形式",
    options=list(_DOC_TYPE_MAP.keys()),
    index=0,
    help="自動 = タスク文から自動判定（Word / Excel / PowerPoint）",
)

_col_gen, _col_clear, _ = st.columns([2, 1, 5])
with _col_gen:
    generate_clicked = st.button(
        "▶ 生成する",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.is_running,
    )
with _col_clear:
    clear_clicked = st.button(
        "✕ クリア",
        use_container_width=True,
        disabled=st.session_state.is_running,
    )

if clear_clicked:
    st.session_state.task_input = ""
    st.session_state.last_result = None
    st.session_state.last_error = None
    st.session_state["_clear_pending"] = True
    st.rerun()

# ---------------------------------------------------------------------------
# Generation logic
# ---------------------------------------------------------------------------

if generate_clicked:
    current_task = st.session_state.task_input_widget
    st.session_state.task_input = current_task

    if not current_task.strip():
        st.warning("⚠️ タスクを入力してください。上のサンプルボタンから選ぶこともできます。")
        st.stop()

    # 前回の結果をクリア
    st.session_state.last_result = None
    st.session_state.last_error = None

    cfg = Config.from_env()
    cfg.backend = "ollama"
    cfg.ollama_url = ollama_url
    cfg.model = model_name
    cfg.template_dir = Path(template_dir)
    cfg.out_dir = Path(out_dir)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    document_type = _DOC_TYPE_MAP[doc_type_label]

    result_holder: dict = {}
    error_holder: dict = {}
    q: queue.Queue[str] = queue.Queue()

    def _run_generation() -> None:
        from office_agent.agent.core import Orchestrator
        from office_agent.llm import create_backend
        from office_agent.tools import ToolRegistry

        try:
            llm = create_backend(cfg)
            registry = ToolRegistry()
            orchestrator = Orchestrator(llm=llm, registry=registry, config=cfg)

            def _on_progress(event: str) -> None:
                q.put(event)

            result = orchestrator.run(
                task=current_task,
                input_files=[],
                out_dir=str(cfg.out_dir),
                template_dir=str(cfg.template_dir),
                document_type=document_type,
                on_progress=_on_progress,
            )
            result_holder.update(result)
        except Exception as exc:
            error_holder["error"] = exc
        finally:
            q.put("__done__")

    thread = threading.Thread(target=_run_generation, daemon=True)
    st.session_state.is_running = True
    thread.start()

    st.subheader("⚙️ 生成ステータス")
    with st.status("⏳ 生成中...", expanded=True) as gen_status:
        stage_placeholder = st.empty()
        progress_bar = st.progress(0.0)

        stage_states = {"stage1": "pending", "stage2": "pending", "stage3": "pending"}
        stage_placeholder.markdown(_build_stage_md(stage_states))

        _stage_event_map = {
            "stage1_start": ("stage1", "running"),
            "stage1_done":  ("stage1", "done"),
            "stage2_start": ("stage2", "running"),
            "stage2_done":  ("stage2", "done"),
            "stage3_start": ("stage3", "running"),
            "stage3_done":  ("stage3", "done"),
        }

        while True:
            try:
                event = q.get(timeout=0.3)
            except queue.Empty:
                continue
            if event == "__done__":
                break
            if event in _stage_event_map:
                key, state = _stage_event_map[event]
                stage_states[key] = state
                stage_placeholder.markdown(_build_stage_md(stage_states))
            if event in _PROGRESS_MSGS:
                _, value = _PROGRESS_MSGS[event]
                progress_bar.progress(value)

        thread.join()

        if "error" in error_holder:
            gen_status.update(label="❌ エラーが発生しました", state="error", expanded=True)
            st.session_state.last_error = error_holder["error"]
        else:
            gen_status.update(label="✅ 生成完了!", state="complete", expanded=False)
            st.session_state.last_result = dict(result_holder)

        st.session_state.is_running = False

# ---------------------------------------------------------------------------
# 永続的な結果表示（session_state から）
# ---------------------------------------------------------------------------

if st.session_state.last_error:
    exc = st.session_state.last_error
    title, suggestion = _friendly_error(exc)
    st.error(f"**{title}**\n\n→ {suggestion}")

if st.session_state.last_result:
    result = st.session_state.last_result
    output_path = result.get("output_path") or (
        (result.get("output_paths") or [None])[0]
    )
    if output_path:
        p = Path(output_path)
        icon = _FILE_ICONS.get(p.suffix, "📄")
        type_label = _FILE_TYPE_LABELS.get(p.suffix, "ファイル")
        size_kb = p.stat().st_size / 1024 if p.exists() else 0

        st.divider()
        st.subheader("✅ 生成結果")
        with st.container(border=True):
            col_info, col_dl = st.columns([3, 1])
            with col_info:
                st.markdown(f"### {icon} {p.name}")
                st.caption(f"{type_label}  ·  {size_kb:.1f} KB  ·  保存先: `{p.parent}`")
            with col_dl:
                if p.exists():
                    with open(p, "rb") as f:
                        st.download_button(
                            label=f"⬇ ダウンロード",
                            data=f.read(),
                            file_name=p.name,
                            type="primary",
                            use_container_width=True,
                        )
    else:
        st.success("✅ 生成完了")

# ---------------------------------------------------------------------------
# Generated files list
# ---------------------------------------------------------------------------

out_path = Path(out_dir)
if out_path.exists():
    office_files = sorted(
        [f for f in out_path.iterdir() if f.suffix in {".docx", ".xlsx", ".pptx"}],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if office_files:
        st.divider()
        st.subheader("📁 生成済みファイル一覧")

        # 拡張子でグループ分け
        groups: dict[str, list[Path]] = {".docx": [], ".xlsx": [], ".pptx": []}
        for f in office_files[:20]:
            if f.suffix in groups:
                groups[f.suffix].append(f)

        for ext, files in groups.items():
            if not files:
                continue
            icon = _FILE_ICONS[ext]
            label = _FILE_TYPE_LABELS[ext]
            st.markdown(f"**{icon} {label}** ({len(files)} 件)")
            for f in files:
                size_kb = f.stat().st_size / 1024
                mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                col1, col2 = st.columns([4, 1])
                col1.markdown(f"&nbsp;&nbsp;`{f.name}`  \n&nbsp;&nbsp;<small>{size_kb:.1f} KB · {mtime}</small>", unsafe_allow_html=True)
                with open(f, "rb") as fh:
                    col2.download_button(
                        label="⬇ DL",
                        data=fh.read(),
                        file_name=f.name,
                        key=f"dl_{f.name}_{f.stat().st_mtime}",
                        use_container_width=True,
                    )
            st.write("")  # グループ間のスペース


if __name__ == "__main__":
    pass
