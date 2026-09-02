"""Simple CLI for amisim."""

import argparse


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="amisim", description="amisim CLI")
    parser.add_argument("name", nargs="?", default="world", help="Name to greet")
    args = parser.parse_args(argv)
    print("Hello, " + args.name)


if __name__ == "__main__":
    main()
