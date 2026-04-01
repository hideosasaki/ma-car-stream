# CLAUDE.md

## プロジェクト概要

Music AssistantからCarPlayへ音楽をストリーミングするICYサーバー。
Raspberry Pi 4上で動作する。詳細はREADME.mdを参照。

## 開発環境

- Raspberry Pi 4 (Debian Bookworm, aarch64)
- Python 3.11+（標準ライブラリのみ、外部パッケージ不要）
- ffmpeg（システムインストール済み）
- snapclient 0.34.0（debパッケージ）
- Music Assistant（Docker, --network=host）

## コードスタイル

- Python: シンプルに、標準ライブラリのみで書く
- シェルスクリプト: bash, POSIX互換意識
- コメント: 英語

## テスト方法

1. `./start_stream.sh` でパイプライン起動
2. MAで曲を再生
3. `curl -s -H "Icy-MetaData: 1" http://localhost:8000/car.mp3 | head -c 50000 | strings | grep StreamTitle` でメタデータ確認
4. ブラウザまたはVLCで `http://localhost:8000/car.mp3` にアクセスして音声確認
5. ログ: `/tmp/icy_server.log`, `/tmp/snapclient.log`

## 重要な注意点

- snapclientはdefaultストリームに割り当てられることがある。「Music Assistant - mae45f014e82ec」ストリームへの割り当てが必要
- FIFOの起動順序が重要: icy_server.py（読み手）→ snapclient（書き手）
- ffmpegをMP3ストリームの途中にID3v2タグを挿入するとMP3フレーム構造が壊れて音が崩れる（試行済み、失敗）
- snapclient 0.26.0（apt版）はsnapserver 0.34.0（MA内蔵）と互換性がない。0.34.0のdebパッケージが必要
- Music AssistantのSnapcast providerを有効にするとMA内蔵のsnapserverが起動する（別途snapserverのインストール不要）

## 次のタスク（優先順）

1. systemdサービス化（icy_server + snapclient の自動起動、起動順序制御）
2. snapclientのストリーム自動割り当てスクリプト
3. 設定値の外部ファイル化
4. Claude Code → MA API → 音楽再生の自動化フロー設計
5. Broadcastsショートカット連携