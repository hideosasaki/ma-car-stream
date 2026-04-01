# ma-car-stream

Music AssistantからCarPlayへ音楽をストリーミングするブリッジサーバー。

## 概要

Raspberry Pi 4上のMusic Assistant（Docker）で再生した音楽を、ICYプロトコル対応のHTTPストリームとして配信し、iPhoneアプリ（Broadcasts）→ CarPlay経由で車のスピーカーから再生する。

## アーキテクチャ

```
Music Assistant (Docker, Raspi4)
  → Snapserver (MA内蔵)
    → snapclient (ホスト側, file出力)
      → FIFO (/tmp/snapstream)
        → icy_server.py (ffmpegでMP3エンコード + ICYメタデータ配信)
          → Tailscale
            → iPhone Broadcasts アプリ
              → CarPlay → 車のスピーカー
```

## 動作確認済みの機能

- Music Assistantからの音声ストリーミング（48kHz/16bit/2ch PCM → MP3 320kbps）
- ICYメタデータ（StreamTitle: アーティスト - 曲名）
- ICY StreamUrl（アルバムアートURL）→ Broadcastsアプリで表示確認済み
- CarPlayでのアーティスト名、曲名、アルバムアート表示
- Tailscale経由での外出先からのアクセス
- 複数クライアント同時接続（ThreadingHTTPServer）
- ffmpegの自動再起動

## ファイル構成

```
ma-car-stream/
├── README.md
├── icy_server.py          # メインサーバー（ICY HTTP配信 + メタデータ取得）
└── start_stream.sh        # パイプライン起動スクリプト
```

## 依存関係

### ホスト側（Raspberry Pi 4, Debian Bookworm）
- Python 3.11+（標準ライブラリのみ）
- ffmpeg（libmp3lame対応）
- snapclient 0.34.0（snapcast/snapcast releases からdebパッケージ）
  - URL: https://github.com/snapcast/snapcast/releases/download/v0.34.0/snapclient_0.34.0-1_arm64_bookworm.deb
  - ※ aptのsnapclientは0.26.0で古すぎて動作しない

### Docker側
- Music Assistant（Snapcast provider有効）
  - snapserverはMA内蔵（v0.34.0）
  - network_mode: host
  - 制御ポート: 1705（TCP）、HTTP API: 1780
  - ストリーミングポート: 動的割り当て（TCPソース）

## セットアップ

### 前提条件
- Music AssistantのSnapcast providerが有効になっていること
- snapclientがインストール済みであること

### snapclientのストリーム割り当て

snapclientは初回接続時に「default」ストリームに割り当てられることがある。
Snapweb（http://localhost:1780）でraspberrypi4クライアントを
「Music Assistant - mae45f014e82ec」ストリームに割り当てる必要がある。

もしくはJSON-RPC APIで割り当て:
```bash
curl -s http://localhost:1780/jsonrpc -d '{
  "id":1,"jsonrpc":"2.0","method":"Group.SetStream",
  "params":{"id":"<group_id>","stream_id":"Music Assistant - mae45f014e82ec"}
}'
```

### 起動

```bash
./start_stream.sh
```

### iPhoneからのアクセス

Broadcastsアプリで以下のURLをカスタムステーションとして登録:
- http://<server-ip>:8000/car.mp3

## 設定値

icy_server.py内の定数:
- `FIFO_PATH`: /tmp/snapstream
- `SAMPLE_RATE`: 48000
- `CHANNELS`: 2
- `MP3_BITRATE`: 320k
- `HTTP_PORT`: 8000
- `ICY_METAINT`: 16000（バイト単位、ICYメタデータ挿入間隔）
- `SNAPSERVER_URL`: http://localhost:1780/jsonrpc
- `BUFFER_SIZE`: 2000（リングバッファのチャンク数）

## TODO

- [ ] systemdサービス化（Raspi起動時の自動起動）
- [ ] snapclientのストリーム自動割り当て（default → Music Assistantストリーム）
- [ ] Claude Code → MA API → 音楽再生の自動化
- [ ] Siri Shortcut / Broadcastsショートカット連携
- [ ] 設定値の外部ファイル化（config.yaml等）
- [ ] エラーハンドリング改善
- [ ] ログローテーション

## 既知の問題

- snapclientが再接続するとdefaultストリームに戻されることがある
- FIFOの読み手（icy_server.py内のffmpeg）が先に起動していないとsnapclientがbroken pipeで落ちる（start_stream.shで起動順序を制御）
- ffmpegのMP3エンコードがRaspi 4のCPUを~10%使用する

## 関連プロジェクト

- 音声AIアシスタント: Siri Shortcut → Webhook → Flask → Claude Code（別リポジトリ）
- Home Assistant連携: ESP32 + ESPHome（検討中）

## 経緯

squeezelite-ESP32でBluetooth A2DP経由の車載再生を試みたが、ESP32のWiFi+BT同時運用が不安定（2分ごとに切断）で断念。Snapcast + ICYストリーミング + Broadcasts（CarPlay対応）の構成に落ち着いた。