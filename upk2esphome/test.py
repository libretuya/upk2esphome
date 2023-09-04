#  Copyright (c) Kuba Szczodrzyński 2023-4-22.

if __name__ == "__main__":
    import sys
    from glob import glob
    from os.path import dirname, join

    from .generator import upk2esphome
    from .opts import Opts

    opts = Opts(
        esphome_block=False,
        common=False,
        web_server=False,
        restart=False,
        uptime=False,
        lt_version=False,
    )

    mask = "*.txt"

    for file in glob(join(dirname(__file__), "tests", mask)):
        if len(sys.argv) == 2 and sys.argv[1] not in file:
            continue
        with open(file, "r") as f:
            d = f.read().strip()
        print(file)
        yr = upk2esphome(d, opts)
        print("\n".join(f"I: {s}" for s in yr.logs))
        print("\n".join(f"W: {s}" for s in yr.warnings))
        print("\n".join(f"E: {s}" for s in yr.errors))
        print(yr.text)
        print("-" * 80)