# TODO: docstring
# vim:ts=4:sw=4:expandtab:fo-=t
def enter_cli_main():
    entry_point("r4a_nao_nlp.cli")


def entry_point(main_module: str):
    import importlib
    import sys

    from r4a_nao_nlp import logging

    logging.init()

    main = importlib.import_module(main_module).main
    sys.exit(main(sys.argv))


if __name__ == "__main__":
    enter_cli_main()