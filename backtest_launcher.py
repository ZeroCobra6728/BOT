from pathlib import Path
import runpy

p = Path(__file__).resolve().parent / "backtest_service.py"
s = p.read_text(encoding="utf-8")
s = s.replace("BTC={btc_final:.2f if btc_final else 0}", "BTC={(btc_final if btc_final is not None else 0):.2f}")
p.write_text(s, encoding="utf-8")
runpy.run_path(str(p), run_name="__main__")
