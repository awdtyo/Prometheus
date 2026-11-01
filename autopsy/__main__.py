import sys

if len(sys.argv) > 1 and sys.argv[1] == "evaluate":
    sys.argv.pop(1)
    from autopsy.evaluation.harness import main as ev_main
    ev_main()
else:
    from autopsy.pipeline import main as pl_main
    pl_main()
