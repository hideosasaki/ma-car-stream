# CLAUDE.md

Music Assistant → CarPlay ICYストリーミングサーバー。詳細はREADME.md参照。

## 開発ルール

- Python: 標準ライブラリのみ、外部パッケージ不要
- コメント: 英語
- デプロイ先: Raspberry Pi 4 (Debian Bookworm, aarch64)

## テスト

1. `sudo systemctl restart icy-stream.service`（または `./start_stream.sh`）
2. MAで曲を再生
3. `curl -s -H "Icy-MetaData: 1" http://localhost:8000/ | head -c 50000 | strings | grep StreamTitle`
4. ログ: `journalctl -u icy-stream.service -f`

## 過去の失敗・知見

- ffmpegでMP3ストリーム途中にID3v2タグ挿入 → フレーム構造が壊れる
- Ogg/Opus → Broadcastsが非対応（接続中のまま再生されない）
- snapclient 0.26.0（apt版）→ snapserver 0.34.0と互換性なし。debパッケージ必要
