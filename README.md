# office-agent

<<<<<<< HEAD
![CI](https://github.com/masahiro-cmd/office-agent/actions/workflows/ci.yml/badge.svg)
=======
> **Fully offline AI agent for generating Word, Excel, and PowerPoint documents
> from natural language — no cloud, no telemetry, no internet required.**
>>>>>>> d07e219 (Add demo image to README)

[![CI](https://github.com/masahiro-cmd/office-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/masahiro-cmd/office-agent/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

ローカル LLM（Ollama / llama.cpp）を使い、自然言語の指示から docx / xlsx / pptx を生成します。
エアギャップ環境・規制産業・データを外部に出せない組織向けに設計されています。

---

<<<<<<< HEAD
=======
## Why Offline?

Most AI document tools send your prompts and file content to cloud APIs.
**office-agent runs entirely on your infrastructure**: all LLM inference stays on-device
via Ollama or llama.cpp, and every file operation is sandboxed to local directories.

Suitable for: government networks, defense-adjacent systems, legal and financial document workflows,
and enterprise environments with strict data residency requirements.

---

## クイックスタート（30秒）

LLM 不要のモックバックエンドで即座に動作確認できます。

```bash
git clone https://github.com/masahiro-cmd/office-agent
cd office-agent
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Word 文書を生成（LLM 不要）
office_agent run --task "月次報告書をWordで作って" --backend mock --out ./out

# Excel を生成（LLM 不要）
office_agent run --task "売上集計Excelを作って" --backend mock --out ./out

# PowerPoint を生成（LLM 不要）
office_agent run --task "製品紹介プレゼンを3枚作って" --backend mock --out ./out
```

生成されたファイルは `./out/` に保存されます。

---

>>>>>>> d07e219 (Add demo image to README)
## 特徴

- **完全オフライン**: インターネット接続不要。すべての処理がローカルで完結する
- **差し替え可能な LLM バックエンド**: Ollama / llama.cpp / Mock の3種類に対応
- **セキュリティ設計**: ToolRegistry ホワイトリスト・ファイル読み取りサンドボックス・テレメトリなし
- **エアギャップ更新**: SHA-256 マニフェスト検証による USB 経由の安全な更新

---

## セキュリティ設計 / Security Architecture

| Control | Implementation |
|---------|----------------|
| **Network isolation** | All LLM calls go to `localhost` only (Ollama `:11434`, llama.cpp `:8080`). Zero outbound internet traffic. |
| **Tool whitelist** | `ToolRegistry` enforces a strict allowlist of 5 tool calls. Any unregistered name raises `PermissionError`. |
| **File sandbox** | Read operations restricted to `ALLOWED_READ_DIRS`. Path traversal (`../`) and symlink escapes are rejected. |
| **No code execution** | VBA generation produces `.bas` files only — no execution, no macro import, no `eval`. |
| **Verified updates** | Air-gap updates use two-level SHA-256 verification (archive + per-file). Ed25519 signature field reserved in manifest schema; SHA-256 is active. |
| **Zero telemetry** | GUI telemetry disabled via `.streamlit/config.toml`. CLI contains no analytics code. |

詳細なセキュリティポリシーは [SECURITY.md](SECURITY.md) を参照してください。

---

## セットアップ

### 必要要件

- Python 3.10 以上
- [Ollama](https://ollama.com/)（推奨）または llama.cpp

### インストール

```bash
git clone https://github.com/masahiro-cmd/office-agent
cd office-agent
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Ollama セットアップ（推奨）

```bash
# 1. インストール（macOS）
brew install ollama
# または https://ollama.com/download からダウンロード

# 2. サーバ起動（バックグラウンド）
ollama serve &

# 3. モデル取得（約2GB、初回のみ）
ollama pull llama3.2:3b

# 4. 接続とモデルを確認
office_agent check

# 5. 動作確認
office_agent run --task "月次報告書をWordで作って" --out ./out
office_agent run --task "売上集計Excelを作って" --out ./out
office_agent run --task "製品紹介プレゼンを3枚作って" --out ./out
```

---

## 使い方

```bash
# ヘルプ
office_agent --help

# モックバックエンドで動作確認（LLM不要）
office_agent run --task "簡単な報告書をWordで作って" --backend mock --out ./out

# Ollama で Word 文書生成
office_agent run --task "月次売上報告書をWordで作って" --out ./out

# Ollama で Excel 生成
office_agent run --task "売上集計ExcelをSUM数式付きで作って" --out ./out

# Ollama で PowerPoint 生成
office_agent run --task "製品紹介プレゼン3枚を作って" --out ./out
```

---

<<<<<<< HEAD
=======
## コマンドリファレンス

### run — 文書生成

```bash
# 基本
office_agent run --task "月次報告書" --out ./out

# 文書種別を明示指定（word / excel / pptx / vba）
office_agent run --task "売上集計" --document-type excel --out ./out
office_agent run --task "製品紹介" --document-type pptx --out ./out

# ディレクトリ内の全ファイルを入力として渡す
office_agent run --task "製品紹介" --document-type pptx --input-dir ./assets --out ./out

# LLM不要のテスト（モックバックエンド）
office_agent run --task "..." --backend mock --out ./out
```

### check — バックエンド接続確認

```bash
# Ollama が起動しているか確認
office_agent check

# バックエンドとモデルを明示指定して確認
office_agent check --backend ollama --model llama3.2:3b
office_agent check --backend mock
```

出力例（Ollama 起動中）:
```
✓ Ollama 起動中: http://localhost:11434
  利用可能モデル: ['llama3.2:3b']
✓ モデル 'llama3.2:3b' は利用可能です
```

### validate — プランJSONの検証

```bash
office_agent validate plan.json
office_agent validate ./out/月次報告書_plan.json
```

### generate-from-plan — 既存プランから直接生成（LLM不使用）

```bash
office_agent generate-from-plan ./out/月次報告書_plan.json --out ./regenerated
office_agent generate-from-plan ./out/売上集計_plan.json --out ./regenerated
```

### update-verify — 更新パッケージの署名検証

```bash
office_agent update-verify ./packages/v1.2.0.tar.gz
```

---

## 編集モード

既存の Office ファイルを AI で更新する場合は `--input` でファイルを渡します。

```bash
# 既存の Word 文書を AI で更新
office_agent run --task "第3章に売上分析を追加して" \
  --input ./reports/monthly.docx --out ./out

# 既存の Excel を更新
office_agent run --task "先月分の売上データを追加し、SUM数式を更新して" \
  --input ./sheets/sales.xlsx --out ./out
```

出力ファイルは `<元ファイル名>_edited.<拡張子>` として保存されます。

---

## テンプレート

`.docx` / `.xlsx` / `.pptx` のテンプレートを所定のディレクトリに置くと自動的に適用されます。

```
templates/
├── word/   ← *.docx を置く（最初に見つかったファイルを使用）
├── excel/  ← 未使用（xlsx はテンプレート不要）
└── pptx/   ← *.pptx を置く（最初に見つかったファイルを使用）
```

```bash
# サンプルテンプレートを生成（python-docx / openpyxl / python-pptx が必要）
python scripts/generate_templates.py
```

---

## エアギャップ展開 / Air-Gap Deployment

インターネットに接続できない環境へのデプロイ手順です。

### オフラインインストール

```bash
# オンライン端末: ホイールを事前ダウンロード
pip download -r requirements.txt -d ./wheels

# USB 等で転送後、オフライン端末でインストール
pip install --no-index --find-links ./wheels -r requirements.txt
```

### LLM モデルの転送

```bash
# オンライン端末: モデルを取得
ollama pull llama3.2:3b

# ~/.ollama/models/ ディレクトリをまるごとオフライン端末にコピー
# コピー後に ollama serve を起動すれば、インターネット不要で動作します
```

### ソフトウェア更新（A端末 → USB → C端末）

1. **A端末（オンライン）** でパッケージを作成し、SHA-256 マニフェストを生成する
2. **USB メモリ** で tar.gz と manifest.json を C端末へ転送する
3. **C端末（オフライン）** で検証・適用する（外部通信なし）

詳細な手順は [SECURITY.md](SECURITY.md) の「5.2 A→B→C 転送手順」を参照してください。

```bash
# オンライン端末: 更新パッケージ作成（マニフェストバージョン 2）
office_agent package-update --version 0.2.0 --out update_packages/

# オフライン端末: 検証（アーカイブ SHA-256 + ファイルごとの SHA-256 の二段階検証）
office_agent verify-update update_packages/office_agent_0.2.0.tar.gz

# オフライン端末: 適用
office_agent apply-update update_packages/office_agent_0.2.0.tar.gz
```

#### モデルファイルの検証

```python
from pathlib import Path
from office_agent.update.verifier import verify_model_file

# manifest["models"]["llama3.2-3b.gguf"] の値と照合
ok = verify_model_file(
    Path("/opt/models/llama3.2-3b.gguf"),
    expected_sha256="<manifest の models フィールドの値>",
)
print("OK" if ok else "MISMATCH — ファイルを再転送してください")
```

---

## GUI（オプション）

Streamlit ベースの GUI を使ったインタラクティブな操作が可能です。

```bash
pip install -e ".[gui]"
streamlit run office_agent/gui.py
```

テレメトリは `.streamlit/config.toml` によりデフォルトで無効化されています。
エアギャップ環境や厳格なセキュリティ要件がある場合は CLI インターフェースを推奨します。

---

>>>>>>> d07e219 (Add demo image to README)
## 設定

`office_agent/config.py` または環境変数で設定します。

| 変数 | デフォルト | 説明 |
|------|-----------|------|
| `OFFICE_AGENT_BACKEND` | `ollama` | LLMバックエンド (`ollama`/`llamacpp`/`mock`) |
| `OFFICE_AGENT_MODEL` | `llama3.2:3b` | 使用モデル名 |
| `OFFICE_AGENT_OLLAMA_URL` | `http://localhost:11434` | Ollama サーバ URL |
| `OFFICE_AGENT_LLAMACPP_URL` | `http://localhost:8080` | llama.cpp サーバ URL |
| `OFFICE_AGENT_OUT_DIR` | `./out` | 出力ディレクトリ |
| `OFFICE_AGENT_ALLOWED_READ_DIRS` | `./,/tmp` | ファイル読み取り許可ディレクトリ |
| `OFFICE_AGENT_OLLAMA_JSON_FORMAT` | `true` | Ollama の JSON 強制モード（`false` で無効化） |
<<<<<<< HEAD
=======
| `OFFICE_AGENT_LLM_TIMEOUT` | `120` | LLM リクエストタイムアウト（秒） |
| `OFFICE_AGENT_MAX_RETRIES` | `3` | LLM JSON パース失敗時の最大リトライ回数 |

---

## トラブルシューティング

### Ollama 接続失敗

```
LLMConnectionError: Cannot connect to Ollama at http://localhost:11434
```

**原因**: Ollama サーバが起動していない。

```bash
ollama serve &          # サーバを起動
ollama pull llama3.2:3b # モデルを取得（初回のみ）
office_agent check      # 接続状態をまとめて確認
```

### タイムアウト

```
LLMTimeoutError: Ollama request timed out after 120s
```

**原因**: モデルが大きすぎる、またはマシンのスペックが不足。

```bash
# タイムアウトを延長
OFFICE_AGENT_LLM_TIMEOUT=300 office_agent run --task "..." --out ./out

# 軽量モデルに切り替え
OFFICE_AGENT_MODEL=llama3.2:1b office_agent run --task "..." --out ./out
```

### JSON パース失敗

```
RuntimeError: LLM did not return valid JSON after 3 attempts
```

**原因**: LLM が JSON 形式でない応答を返した。

```bash
# リトライ回数を増やす
OFFICE_AGENT_MAX_RETRIES=5 office_agent run --task "..." --out ./out

# モックでプランを作成し、generate-from-plan を使う
office_agent run --task "..." --backend mock --out ./out
# plan.json を手動で編集してから
office_agent generate-from-plan ./out/<title>_plan.json --out ./out
```
>>>>>>> d07e219 (Add demo image to README)

---

## テスト

```bash
pytest tests/ -v
pytest tests/ -v --cov=office_agent
```

---

<<<<<<< HEAD
## 更新システム

```bash
# オンライン端末: 更新パッケージ作成
office_agent package-update --version 0.2.0 --out update_packages/

# オフライン端末: 検証
office_agent verify-update update_packages/office_agent_0.2.0.tar.gz

# オフライン端末: 適用
office_agent apply-update update_packages/office_agent_0.2.0.tar.gz
```

---

=======
>>>>>>> d07e219 (Add demo image to README)
## プロジェクト構成

```
office-agent/
├── office_agent/          # メインパッケージ
│   ├── agent/             # オーケストレータ
│   ├── llm/               # LLM アダプタ層
│   ├── tools/             # Office 生成ツール
│   ├── schemas/           # JSON スキーマ
│   └── update/            # 更新システム
├── templates/             # Office テンプレート
├── tests/                 # テスト
└── out/                   # 生成物出力先
```

<<<<<<< HEAD
=======
---

## 既知の制約 / Known Constraints

The following constraints are by design or currently unimplemented.

| 項目 | 内容 |
|------|------|
| LLM 品質依存 | 出力品質はモデルに依存。複雑な指示は `--backend mock` + `generate-from-plan` 推奨 |
| VBA 実行不可 | `.bas` ファイルを生成するのみ。Excel への自動インポートや実行はしない |
| 署名検証 | Ed25519 フィールドはマニフェストスキーマに予約済み。現在は SHA-256 ハッシュ検証が有効 |
| オフライン専用 | LLM バックエンドはローカルホストのみ。外部 API 呼び出しは意図的に不可 |
| Python 要件 | Python 3.10 以上必須 |
| LLM なしで使えるコマンド | `validate`, `generate-from-plan`, `verify-update`, `apply-update` は LLM 不要 |

---

>>>>>>> d07e219 (Add demo image to README)
## ライセンス

MIT
## Demo / デモ

### Input

```
月次営業報告書をWordで作って
```

### Output

![Generated Document](docs/demo.png)

This document was generated entirely offline using a local LLM.

No internet connection was used. No data was sent externally.
