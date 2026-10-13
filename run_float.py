from pathlib import Path
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from float_app.app import main
    raise SystemExit(main())

