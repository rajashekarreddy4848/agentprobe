"""The `agentprobe` command: dashboard and export."""
import argparse

from . import dashboard


def main(argv=None):
    parser = argparse.ArgumentParser(prog="agentprobe", description="Dashboard for agentprobe test runs.")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("dashboard", help="serve the dashboard for a run store")
    serve.add_argument("db", help="run store created with: pytest --agentprobe-store=runs.db")
    serve.add_argument("--port", type=int, default=8787)

    export = sub.add_parser("export", help="write a static copy of the dashboard")
    export.add_argument("db")
    export.add_argument("out_dir")
    export.add_argument("--home", help='link back to your site, e.g. "../" if the dashboard is in a subfolder')

    args = parser.parse_args(argv)
    if args.command == "dashboard":
        dashboard.serve(args.db, args.port)
    else:
        print(f"wrote {dashboard.export(args.db, args.out_dir, home_url=args.home)}")
