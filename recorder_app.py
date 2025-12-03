import os, sys, time, json, wave, shutil, subprocess, collections
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "WinLocalRecorder"
CFG_DIR = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / APP_NAME
CFG_DIR.mkdir(parents=True, exist_ok=True)
CFG_FILE = CFG_DIR / "config.json"

def load_cfg():
    if CFG_FILE.exists():
        try:
            return json.load(open(CFG_FILE, "r", encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_folder": str(Path.home() / "Music"),
        "rate": 44100,
        "channels": 1,
        "device_index": None,
        "format": "wav",  # wav | flac
        "gain_db": 0,
    }

def save_cfg(cfg):
    try:
        json.dump(cfg, open(CFG_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass

# ===== 録音バックエンド: sounddevice =====
class SDRecorder:
    def __init__(self, rate=44100, channels=1, blocksize=1024, device_index=None, scope_secs=2.0, gain_db=0):
        import sounddevice as sd, numpy as np
        self.sd = sd; self.np = np
        self.rate, self.channels, self.blocksize = rate, channels, blocksize
        self.device_index = device_index
        self._stream = None; self._running = False; self._start = 0
        self.scope_buf = collections.deque(maxlen=int(scope_secs * rate))
        self._level = 0
        self.mode = "wav"
        self._wf = None; self._sf = None
        self.gain_db = gain_db

    def list_input_devices(self):
        return [(i, d["name"]) for i, d in enumerate(self.sd.query_devices()) if d.get("max_input_channels",0)>0]

    def set_device_index(self, idx): self.device_index = idx
    def set_gain_db(self, db): self.gain_db = db

    def start(self, out_path, fmt="wav"):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        self.mode = fmt
        if fmt == "wav":
            self._wf = wave.open(str(out_path), "wb")
            self._wf.setnchannels(self.channels)
            self._wf.setsampwidth(2)
            self._wf.setframerate(self.rate)
        elif fmt == "flac":
            import soundfile as sf
            self._sf = sf.SoundFile(str(out_path), mode="w", samplerate=self.rate, channels=self.channels, subtype="PCM_16", format="FLAC")
        else:
            raise ValueError("unknown format")

        def cb(indata, frames, time_info, status):
            if status: pass
            g = float(10.0 ** (self.gain_db / 20.0))
            data = self.np.clip(indata * g, -1.0, 1.0)
            if self.mode == "wav":
                pcm16 = (data * 32767).astype(self.np.int16)
                self._wf.writeframes(pcm16.tobytes())
            else:
                import soundfile as sf  # noqa
                pcm16 = (data * 32767).astype("int16")
                self._sf.write(pcm16)
            mono = data.mean(axis=1) if data.ndim>1 else data
            self.scope_buf.extend(mono.tolist())
            rms = float(self.np.sqrt(self.np.mean(self.np.square(mono)))) if len(mono) else 0.0
            self._level = max(0, min(int(rms * 300), 100))

        self._stream = self.sd.InputStream(samplerate=self.rate, channels=self.channels, blocksize=self.blocksize, dtype='float32', device=self.device_index, callback=cb)
        self._stream.start(); self._running=True; self._start=time.time()

    def stop(self):
        if not self._running: return
        self._running=False
        try: self._stream.stop(); self._stream.close()
        except Exception: pass
        if self.mode == "wav":
            try: self._wf.close()
            except Exception: pass
        else:
            try: self._sf.close()
            except Exception: pass

    def is_running(self): return self._running
    def elapsed(self): return int(time.time()-self._start) if self._start else 0
    def level(self): return self._level

# ===== GUI =====
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WinLocalRecorder"); self.geometry("840x420"); self.resizable(True, False)

        self.cfg = load_cfg()
        self.rec = SDRecorder(rate=self.cfg["rate"], channels=self.cfg["channels"], device_index=self.cfg["device_index"], scope_secs=2.0, gain_db=self.cfg.get("gain_db",0))
        self.devs = self.rec.list_input_devices()

        self.var_folder = tk.StringVar(value=self.cfg["last_folder"])
        self.var_device = tk.StringVar()
        self.var_status = tk.StringVar(value="状態: 待機中")
        self.var_elapsed = tk.StringVar(value="時間: 00:00:00")
        self.var_file = tk.StringVar(value="")
        self.var_fmt = tk.StringVar(value=self.cfg.get("format","wav"))       # wav / flac
        self.var_gain = tk.IntVar(value=int(self.cfg.get("gain_db",0)))

        self._build_ui(); self._init_device_selection()
        self.after(100, self._ui_loop)

    def _build_ui(self):
        pad={'padx':8,'pady':6}
        f1=ttk.Frame(self); f1.pack(fill='x', **pad)
        ttk.Label(f1,text="保存フォルダ").pack(side='left')
        ent = ttk.Entry(f1,textvariable=self.var_folder); ent.pack(side='left',fill='x',expand=True,padx=6)
        ttk.Button(f1,text="参照",command=self._choose_folder).pack(side='left')
        ent.bind("<FocusOut>", lambda e: self._persist_folder())

        f2=ttk.Frame(self); f2.pack(fill='x', **pad)
        ttk.Label(f2,text="デバイス").pack(side='left')
        self.cmb_dev=ttk.Combobox(f2,textvariable=self.var_device,state='readonly',width=52)
        self.cmb_dev.pack(side='left',fill='x',expand=True,padx=6)
        ttk.Button(f2,text="更新",command=self._refresh_devices).pack(side='left',padx=(0,6))
        ttk.Label(f2,text="形式").pack(side='left')
        self.cmb_fmt=ttk.Combobox(f2,textvariable=self.var_fmt,values=["wav","flac"],state='readonly',width=6)
        self.cmb_fmt.pack(side='left',padx=(2,6))
        ttk.Label(f2,text="ゲイン(dB)").pack(side='left')
        self.cmb_gain=ttk.Combobox(f2,textvariable=self.var_gain,values=[-20,-12,-6,0,6,12,18,24],state='readonly',width=5)
        self.cmb_gain.pack(side='left')
        self.cmb_gain.bind("<<ComboboxSelected>>", lambda e: self._persist_gain())

        f3=ttk.Frame(self); f3.pack(fill='x', **pad)
        self.btn_toggle=ttk.Button(f3,text="● 録音開始",command=self._toggle_rec); self.btn_toggle.pack(side='left')
        ttk.Label(f3,textvariable=self.var_status).pack(side='left',padx=10)
        ttk.Label(f3,textvariable=self.var_elapsed).pack(side='right')

        f4=ttk.Frame(self); f4.pack(fill='x', **pad)
        ttk.Label(f4,text="波形").pack(anchor='w')
        self.canvas=tk.Canvas(f4,bg="#1e2a35",height=190,highlightthickness=1,highlightbackground="#3a4a59")
        self.canvas.pack(fill='x',expand=True)

        f5=ttk.Frame(self); f5.pack(fill='x', **pad)
        ttk.Label(f5,text="レベル").pack(side='left')
        self.pb=ttk.Progressbar(f5,maximum=100,length=520); self.pb.pack(side='left',padx=6)

        f6=ttk.Frame(self); f6.pack(fill='x', **pad)
        ttk.Label(f6,text="保存ファイル").pack(side='left')
        ttk.Entry(f6,textvariable=self.var_file).pack(side='left',fill='x',expand=True,padx=6)
        ttk.Button(f6,text="フォルダを開く",command=self._open_folder).pack(side='left')

        self.rec_indicator=self.canvas.create_oval(10,10,26,26,fill="",outline="")
        self.rec_text=self.canvas.create_text(40,18,text="",fill="#ff5555",font=("Segoe UI",10,"bold"))

        try: ttk.Style().theme_use('clam')
        except tk.TclError: pass

    def _init_device_selection(self):
        names=[f"[{i}] {n}" for i,n in self.devs]
        self.cmb_dev['values']=names
        idx=0
        if self.cfg.get("device_index") is not None:
            for k,(i,_) in enumerate(self.devs):
                if i==self.cfg["device_index"]: idx=k; break
        if names:
            self.cmb_dev.current(idx); self.var_device.set(names[idx])
        else:
            self.var_device.set("（入力デバイスが見つかりません）")

    def _persist_folder(self):
        if self.var_folder.get():
            self.cfg["last_folder"]=self.var_folder.get(); save_cfg(self.cfg)

    def _persist_format(self):
        self.cfg["format"]=self.var_fmt.get() or "wav"; save_cfg(self.cfg)

    def _persist_gain(self):
        db=int(self.var_gain.get())
        self.cfg["gain_db"]=db; save_cfg(self.cfg)
        self.rec.set_gain_db(db)

    def _choose_folder(self):
        d=filedialog.askdirectory(initialdir=self.var_folder.get() or str(Path.home()))
        if d: self.var_folder.set(d); self._persist_folder()

    def _refresh_devices(self):
        self.devs=self.rec.list_input_devices(); self._init_device_selection()

    def _toggle_rec(self):
        try:
            if not self.rec.is_running():
                sel=self.var_device.get()
                if self.devs and sel and sel.startswith('['):
                    try:
                        idx=int(sel.split(']')[0].replace('[','').strip())
                        self.rec.set_device_index(idx); self.cfg["device_index"]=idx
                    except Exception: pass
                folder=os.path.expandvars(os.path.expanduser(self.var_folder.get() or ""))
                if not os.path.isdir(folder):
                    messagebox.showerror("エラー","保存フォルダが存在しません。\nNASは \\\\NAS\\share 形式で接続してください。"); return
                self.cfg["last_folder"]=folder; save_cfg(self.cfg)

                fmt=(self.var_fmt.get() or "wav").lower(); self._persist_format()
                self._persist_gain()

                ts=datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path=os.path.join(folder, f"rec_{ts}.{fmt}")
                self.rec.start(out_path, fmt=fmt)
                self.var_file.set(out_path)
                self.var_status.set(f"状態: 録音中（{fmt.upper()} / {self.cfg['gain_db']} dB）")
                self.btn_toggle.config(text="■ 録音停止")
            else:
                self.rec.stop()
                self.var_status.set("状態: 保存完了")
                self.btn_toggle.config(text="● 録音開始")
                self.pb['value']=0
                self.canvas.itemconfig(self.rec_indicator, fill="", outline=""); self.canvas.itemconfig(self.rec_text, text="")
        except Exception as e:
            messagebox.showerror("録音エラー", str(e))

    def _open_folder(self):
        if os.path.isdir(self.var_folder.get()): os.startfile(self.var_folder.get())

    def _ui_loop(self):
        if self.rec.is_running():
            sec=self.rec.elapsed(); h,rem=divmod(sec,3600); m,s=divmod(rem,60)
            self.var_elapsed.set(f"時間: {h:02}:{m:02}:{s:02}")
            self.pb['value']=self.rec.level()
            self._draw_waveform()
            # 点滅REC
            if int(time.time()*5)%2==0: color="#ff3333"
            else: color="#aa2222"
            self.canvas.itemconfig(self.rec_indicator, fill=color, outline=color)
            self.canvas.itemconfig(self.rec_text, text="REC")
        else:
            self.var_elapsed.set("時間: 00:00:00")
        self.after(100, self._ui_loop)

    def _draw_waveform(self):
        W=int(self.canvas.winfo_width()); H=int(self.canvas.winfo_height())
        self.canvas.delete("wave")
        buf=list(self.rec.scope_buf)
        if not buf: return
        step=max(1, int(len(buf)/max(1,W)))
        pts=buf[-step*W::step]
        mid=H//2; amp=(H*0.45)
        last_x=0
        for x in range(len(pts)):
            y=int(mid - max(-1.0, min(1.0, pts[x])) * amp)
            if x>0:
                self.canvas.create_line(last_x, prev_y, x, y, fill="#66d9ef", tags="wave")
            prev_y=y; last_x=x
        self.canvas.create_line(0, mid, W, mid, fill="#2c3e50", tags="wave")

def main():
    try:
        import sounddevice, numpy  # noqa
    except Exception as e:
        messagebox.showerror("依存エラー", "sounddevice と numpy が必要です。\n"+str(e)); sys.exit(2)
    App().mainloop()

if __name__ == "__main__":
    main()
