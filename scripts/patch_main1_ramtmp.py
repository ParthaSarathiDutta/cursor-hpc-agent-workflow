#!/usr/bin/env python3
"""One-off: fix main1.py ramtmp symlink race on a run folder (multiprocess import)."""
from __future__ import annotations

import sys
from pathlib import Path

OLD = """#----- create ram based tmp -----
if not 'ramtmp' in blast.runtime:
    import tempfile, os
    from pathlib import Path
    tmp = tempfile.mkdtemp(prefix="blastff_",dir='/dev/shm')
    if not Path(tmp).exists():
        blast.mpy.ERROR(f"cannot create tmp directory,\\n{tmp}")
    else: blast.logger.info(f"ram based tmp directory at {tmp}")
    tmp_dir = blast.conf.get('lmp',{}).get('tmp_dir','tmp')
    try: blast.cmd.ln(tmp,tmp_dir)
    except: blast.mpy.ERROR(f"cannot symlink {tmp} to '{tmp_dir}'")
    blast.runtime['ramtmp'] = tmp"""

NEW = """#----- create ram based tmp -----
if not 'ramtmp' in blast.runtime:
    import tempfile, os, shutil
    from pathlib import Path
    tmp_dir = blast.conf.get('lmp',{}).get('tmp_dir','tmp')
    p_tmp = Path(tmp_dir)
    if p_tmp.is_symlink():
        blast.runtime['ramtmp'] = str(p_tmp.resolve())
    else:
        if p_tmp.exists():
            shutil.rmtree(p_tmp) if p_tmp.is_dir() else p_tmp.unlink()
        tmp = tempfile.mkdtemp(prefix="blastff_",dir='/dev/shm')
        if not Path(tmp).exists():
            blast.mpy.ERROR(f"cannot create tmp directory,\\n{tmp}")
        else:
            blast.logger.info(f"ram based tmp directory at {tmp}")
        try:
            blast.cmd.ln(tmp, tmp_dir)
        except Exception:
            blast.mpy.ERROR(f"cannot symlink {tmp} to '{tmp_dir}'")
        blast.runtime['ramtmp'] = tmp"""


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "")
    if not path.is_file():
        print(f"Usage: {sys.argv[0]} /path/to/main1.py", file=sys.stderr)
        return 1
    text = path.read_text()
    if OLD not in text:
        if NEW.split("\n", 3)[3] in text:
            print("already patched")
            return 0
        print("expected block not found", file=sys.stderr)
        return 1
    path.write_text(text.replace(OLD, NEW, 1))
    print(f"patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
