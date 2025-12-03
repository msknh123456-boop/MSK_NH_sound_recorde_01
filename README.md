# MSK_NH_sound_recorde_01

Windows 向けのローカル録音ツール **WinLocalRecorder**。`recorder_app.py` の GUI で以下の機能を提供しています。

## 共有したい実装ポイント

- **入力波形の可視化**（`recorder_app.py:150-166`, `_draw_waveform`）  
  録音コールバックで保持したモノラル化バッファを Canvas に描画し、直近数秒の音声をリアルタイム表示します。
- **ゲイン調整 UI**（`recorder_app.py:138-143`, `_persist_gain`）  
  dB ステップを Combobox から選択し、`SDRecorder` へ即反映。設定は `%APPDATA%\WinLocalRecorder\config.json` に保存します。
- **入力レベルメータ**（`recorder_app.py:155-158`, `_ui_loop`）  
  RMS で計算したレベルを `ttk.Progressbar` に反映し、クリッピング前の状態を把握できます。
- **ソフト内でのゲイン処理**（`recorder_app.py:68-82`）  
  浮動小数のストリームに指定 dB を適用し、`np.clip` で -1.0～1.0 に収めることで簡易な音量調整を完結させています。フィルタ処理を同コールバックに追加すれば EQ やノイズ抑制も可能です。

## 使い方

1. `run_recorder.bat` を実行すると仮想環境の作成・依存導入・GUI 起動まで自動で行われます。
2. 保存フォルダ・デバイス・形式・ゲインを選択して「録音開始」。停止すると `rec_YYYYMMDD_HHMMSS.wav/flac` が保存されます。
